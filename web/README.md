# web/ — App shell da plataforma de anotação

SPA leve **sem build step**: ES modules nativos + CSS puro. Konva (vendored em
`web/vendor/`) é usado apenas pelo canvas (`web/src/canvas/`, dono: subagente
anno-web-canvas). Este diretório cobre o **app shell**: dashboard, wizard de
criação, página do projeto (tabs), autosave e a tela de anotação em 3 zonas.

## Como rodar

### Contra a API real

1. Suba a API (FastAPI, prefixo `/annotate`) conforme `api/README.md`.
2. Sirva esta pasta estaticamente **na mesma origem do nginx** (recomendado) ou
   aponte para outra origem:

   ```bash
   cd web
   python -m http.server 8080
   # abra http://localhost:8080/
   ```

3. Para API em outra origem, edite `index.html` e defina antes dos módulos:

   ```html
   <script>window.__API_BASE__ = "http://localhost:8000/annotate";</script>
   ```

4. Na primeira chamada, o app pede a chave de API (header `X-API-Key`) uma vez
   e guarda em `sessionStorage`.

### Com o servidor de mock (sem backend)

```bash
cd web
python -m http.server 8080
# abra http://localhost:8080/?mock
```

O mock (`web/mocks/server.js`) faz monkeypatch de `fetch` e implementa um
subconjunto dos contratos da seção 7 em memória (projeto demo "demo-placas"
com 12 imagens). O canvas real ainda não existindo, a tela de anotação cai
automaticamente no stub `web/mocks/anno-canvas-stub.js` (div colorido que loga
as chamadas e permite criar/aceitar caixas).

Limitação conhecida do mock: requisições de `<img>` (thumbs) não passam pelo
`fetch` monkeypatchado, então as thumbnails aparecem quebradas no modo `?mock`
— o restante (dados, labels, drafts, commit) funciona normalmente.

## Estrutura

```
web/
├── index.html            entry; define window.__API_BASE__ / ?mock
├── styles/main.css       todo o CSS
├── src/
│   ├── app.js            router por hash + chrome
│   ├── config.js         API_BASE
│   ├── api.js            wrapper fetch (X-API-Key, erros JSON, upload XHR)
│   ├── auth.js           chave de API + usuário (sessionStorage/localStorage)
│   ├── autosave.js       PEÇA CRÍTICA (§9): IndexedDB + fila de sync + retry
│   ├── ui.js             helpers de DOM, badges, paleta de classes, modal
│   ├── canvas/           (outro subagente — NÃO editar aqui)
│   └── views/
│       ├── dashboard.js  lista de projetos
│       ├── wizard.js     criação em 3 passos (modelo | manual | importar)
│       ├── project.js    header + tabs
│       ├── annotate.js   tela 3 zonas + fila inteligente + atalhos D/A/N
│       ├── images.js     grade de thumbs, upload drag-and-drop, pré-anotar
│       ├── classes.js    lista ordenada + adicionar no final (irreversível)
│       ├── importExport.js  import com dry-run + export com manifest
│       ├── jobs.js       status dos jobs (Fase 1: submissão Slurm manual)
│       └── settings.js   PATCH do project.yaml (classes somente-leitura)
└── mocks/
    ├── server.js         API falsa via monkeypatch de fetch (?mock)
    └── anno-canvas-stub.js  stub da interface congelada do canvas
```

## Contrato com o canvas (congelado)

`web/src/canvas/anno-canvas.js` exporta
`createAnnoCanvas(container, options) => handle`; ver assinatura exata em
`web/mocks/anno-canvas-stub.js`. O shell importa o módulo real com
fallback para o stub.

## Autosave (seção 9)

`src/autosave.js`: cada `onChange` do canvas grava o draft no IndexedDB
(`anno-drafts`, chave `${slug}/${img}`) **antes** de qualquer rede. O `PUT` do
draft dispara por 5 ops OU 30 s OU navegação OU `visibilitychange=hidden` —
o que vier primeiro (debounce de 500 ms). Falhas → retry com backoff
exponencial; `409` → aviso não-destrutivo e o rascunho local é preservado.
Ao abrir uma imagem, se houver rascunho local divergente do servidor, um
banner oferece **Restaurar/Descartar**. `Done` → `POST .../commit` → 🟢 →
próxima imagem.

## Nota de autenticação em imagens

`<img>` e texturas de canvas não enviam headers. As URLs de `thumb`/`full`/
`tiles` levam a chave como `?api_key=` (ver `api.js`); o backend deve aceitar
esse parâmetro como alternativa ao `X-API-Key` apenas nos endpoints de imagem.
