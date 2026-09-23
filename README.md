# anotation-platform

Plataforma de pré-anotação estilo Roboflow para datasets YOLO de armadilhas de moscas (fly-det).

**Repositório independente:** backend, interface web, contratos, importação/exportação
e engine de pré-anotação estão aqui. Não é necessário clonar ou instalar `fly-det`
ou `fly_det_api`. O fly-det apenas referencia este repositório como submódulo Git;
isso não cria uma dependência de execução. As bibliotecas públicas são instaladas pelo uv.

Não incluímos datasets nem pesos de modelos. Para anotação manual, nenhum modelo é necessário.

---

## Rodando pela primeira vez

### Pré-requisitos
- Linux com **Python 3.12+** e [**uv**](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`).
- Um navegador moderno (Chrome/Firefox).
- (Opcional, para pré-anotação) um checkpoint Ultralytics YOLO `.pt` de origem confiável.
  Carregar checkpoints desconhecidos pode executar código; não aceite pesos de usuários não confiáveis.

### 1. Instalar

```bash
git clone https://github.com/marcospaulo429/anotation-platform.git
cd anotation-platform
uv sync --locked --extra api --extra dev
```

Para usar pré-anotação ou criar projetos a partir de um checkpoint:

```bash
uv sync --locked --extra api --extra engine --extra dev
```

O extra `engine` instala Ultralytics, Supervision e PyTorch. O lock usa wheels CPU
no Linux; a primeira instalação é maior. A API e a anotação manual não precisam desse extra.
Não rode `make install-api` depois da instalação completa: a sincronização exata pode
remover o extra `engine`. Use sempre o conjunto de extras que pretende manter.

Os atalhos `make install-api` e `make install-engine` executam esses mesmos comandos.
Quando usado como submódulo de outro projeto, execute os comandos dentro desta pasta.

### 2. Subir a plataforma (API + interface juntas)

```bash
export ANNOTATE_ROOT="$PWD/.scratch/data"
export ANNOTATE_API_HOST=127.0.0.1
read -rsp 'Chave de acesso local: ' API_KEY; printf '\n'
export API_KEY
uv run --no-sync annotate-api
```

- `API_KEY` — a senha da plataforma (a interface vai pedir na 1ª vez). **Obrigatória** — sem ela o servidor não sobe (erro `API_KEY não configurada` é esperado se você rodar sem definir).
- `ANNOTATE_ROOT` — caminho absoluto dos dados; `.scratch/` é ignorado pelo Git.
  Para uso permanente, escolha um diretório persistente com backup, fora do checkout.
  No cluster fly-det, use `/raid/user_marcospaulo/annotate`, nunca a home.
- `ANNOTATE_API_HOST=127.0.0.1` limita o servidor à máquina local.
- `ANNOTATE_API_PORT` permite trocar a porta 5200 se ela estiver ocupada.
- A **interface web já é servida pela própria API** — não precisa de servidor separado.

O terminal permanece ocupado pelo servidor; encerre com Ctrl+C. Em outro terminal,
entre nesta pasta e exporte novamente `ANNOTATE_ROOT` antes de usar as CLIs.

Abra **http://localhost:5200/** → informe a chave → pronto.

> **Dica (dev):** se algo parecer não atualizar após editar código, force **Ctrl+Shift+R** (o navegador cacheia módulos).

### 3. Criar o primeiro projeto

Clique **+ Novo projeto** e siga o wizard de 3 passos:

1. **Nome** — o slug é gerado automaticamente.
2. **Caminho dos dados** — escolha um:
   - **Pré-anotar com modelo** → aponte um `.pt`; as **classes vêm do checkpoint** (você não digita nada).
   - **Manual do zero** → você define as classes (ordem = índice YOLO).
   - **Importar dados já anotados** → a interface desse caminho ainda está em integração;
     para importar hoje, crie um projeto manual com as classes na ordem do dataset
     e use a aba Importar/Exportar ou a CLI abaixo.
3. **Config** — thresholds da pré-anotação (se houver). **Criar projeto.**

### 4. Subir imagens e pré-anotar

- Aba **Imagens** → arraste JPG/JPEG/PNG; as dimensões precisam corresponder ao projeto
  (1920×1080 por padrão). Os originais não são redimensionados.
- Botão **Pré-anotar** → registra o job. *A submissão ao cluster (Slurm/GPU) é manual/aprovada — nunca automática.*
- Para pré-anotar localmente em CPU (teste), rode no terminal:
  ```bash
  nice -n 19 uv run --no-sync annotate-engine --project "$ANNOTATE_ROOT/projects/meu-projeto"
  ```

Substitua `meu-projeto` pelo slug criado. O checkpoint configurado precisa existir no
servidor que executa o engine. `--dry-run` lista o trabalho sem inferência; nenhuma
imagem é enviada a serviços externos. O engine processa uma imagem por vez.
Slurm e o container do cluster são integrações opcionais, não pré-requisitos locais.

### 5. Anotar (a tela principal)

Aba **Anotar**. A imagem abre enquadrada na área disponível; use zoom ou varredura
para revisar objetos pequenos. Tiles são recortes dos originais. Caixas tracejadas = sugestão do modelo.

**Atalhos:**

| Tecla | Ação |
|---|---|
| **H** | ✋ mão (mover a imagem) |
| **B** | ▣ desenhar bounding box |
| `W` | alterna mão ↔ desenho |
| `T` | modo varredura por tiles (Enter marca tile visto) |
| `L` | lupa (3×) |
| `C` | mira (crosshair) |
| `1`–`9` | trocar classe da caixa selecionada |
| `Del` | apagar caixa |
| `N` | nova classe (adiciona no final) |
| `D` / `A` | próxima / anterior imagem |
| `Ctrl+Z` / `Ctrl+Y` | desfazer / refazer |

Clique numa caixa tracejada para **aceitar** a sugestão do modelo. Arraste cantos para ajustar.
O **autosave** grava a cada operação (● saved no topo) e sobrevive a fechar a aba.

**Done ✓** confirma a imagem e vai para a próxima.

### 6. Exportar para treino

Aba **Importar/Exportar** → **Exportar** → gera `exports/v1/` com `data.yaml` e labels YOLO,
utilizáveis por ferramentas compatíveis, sem exigir fly-det. Apenas labels confirmadas
em `manual/` entram; drafts não entram no treino.

**Confira o agrupamento antes de treinar:** a implementação atual considera placa o
prefixo do nome da imagem antes do primeiro `_` (ou o nome sem extensão inteiro).
Isso só evita leakage se os seus nomes realmente codificarem a placa. A função Python
`export_dataset(..., plate_key=...)` aceita uma regra explícita para outros datasets.
O split usa placas ordenadas, podendo gerar partições vazias em conjuntos pequenos.

### Importar anotações existentes

O importador atual lê diretórios acessíveis **no servidor**, não pastas do computador
do navegador. Os nomes de classes devem vir do `names` do `data.yaml` ou de uma lista
ordenada externa: arquivos `.txt` YOLO contêm apenas IDs, não nomes.

```bash
uv run --no-sync python scripts/import_dataset.py \
  --project "$ANNOTATE_ROOT/projects/meu-projeto" \
  --images /caminho/dataset/images --labels /caminho/dataset/labels
```

Revise o relatório do dry-run; acrescente `--execute` para gravar. Importações válidas
entram em `manual/`; imagens sem label ficam sem anotação. Os arquivos de origem podem
ser ligados por hardlink: mantenha fontes imutáveis ou use `--copy` na importação.

## Arquitetura E Distribuição

- `contracts`: schemas Pydantic e validação YOLO compartilhados pelas camadas Python.
- `api`: FastAPI, chave de acesso, projetos e operações sobre arquivos.
- `engine`: Ultralytics para detecção, Supervision para tiles e NMS; imports pesados lazy.
- `dataset_ops`: importação e snapshots de export usados pela API e pelas CLIs.
- `web`: SPA ES modules + Konva incluídos no repositório e no wheel; sem npm/build frontend.
- Dados: `<ANNOTATE_ROOT>/projects/<slug>/`, com `project.yaml`, imagens,
  labels `pre/`, `pre_meta/`, `drafts/`, `manual/`, eventos e `exports/vN/`.

O filesystem é a fonte da verdade; não há banco obrigatório. Para backup, preserve toda
a raiz dos dados, não só as imagens. Rascunhos ainda não sincronizados ficam no navegador.

```bash
uv build
```

Gera sdist e wheel em `dist/`. O wheel contém API e interface estática; `ANNOTATE_WEB_DIR`
é apenas um override opcional. O sdist também contém testes e scripts de import/export.
A instalação de um wheel por pip não aplica as fontes de índice do uv: para obter os
mesmos wheels CPU do ambiente de desenvolvimento, prefira o checkout/sdist com `uv sync --locked`.

## Limitações Atuais

- Uso local confiável: chave compartilhada, sem contas individuais nem isolamento multiusuário.
- Não exponha diretamente à internet. Pesos e caminhos de import devem ser controlados pelo operador;
  URLs de mídia atualmente incluem a chave e podem aparecer em logs.
- O botão Pré-anotar registra uma solicitação, mas não executa nem acompanha um job real.
  Use a CLI em CPU; o template Slurm é específico do cluster e exige configuração externa.
- Importação pelo wizard e diff visual entre gerações de modelos ainda não estão completos.
  Independência de instalação não implica que todas as funcionalidades planejadas estejam prontas.

## Problemas Comuns

- `API_KEY não configurada`: exporte a chave no terminal que inicia a API.
- `Address already in use`: use outra `ANNOTATE_API_PORT`; não encerre servidores alheios.
- `No module named ultralytics`: sincronize com `--extra api --extra engine --extra dev`.
- Permissão negada em `/raid`: defina `ANNOTATE_ROOT` para um caminho gravável antes de iniciar.
- Interface antiga: reinicie a API após alterações Python e recarregue o navegador.
- Erro de save: preserve o draft local; verifique a resposta da API e o log antes de apagar dados.

---

## Comandos de referência

```bash
make install-api      # instala API + dev
make install-engine   # API + engine + dev — necessário p/ pré-anotar
make check            # ruff + pytest, sem alterar o ambiente instalado

# Rodar a plataforma
API_KEY=... ANNOTATE_ROOT=... uv run --no-sync annotate-api

# Pré-anotar um projeto via CLI (CPU)
uv run --no-sync annotate-engine --project <dir-do-projeto> [--force] [--dry-run]

# Importar / exportar dataset via CLI
uv run --no-sync python scripts/import_dataset.py --project <dir> --images <dir> --labels <dir> [--execute]
uv run --no-sync python scripts/export_dataset.py --project <dir> --user <nome>
```

## Layout

```
src/annotation_platform/
├── contracts/    # Schemas Pydantic (project.yaml, draft, pre_meta, status.jsonl) — fonte única
├── engine/       # CLI de pré-anotação (predict+SAHI → labels/pre + pre_meta + status.jsonl)
└── api/          # FastAPI: projetos, upload, tiles, draft/commit, import, export
web/              # SPA (canvas de anotação)
scripts/          # Importadores (DS-F2, avaliações antigas) e tooling de export
slurm/            # Templates sbatch — NUNCA submeter job sem aprovação explícita
tests/            # Contratos automatizados (pytest)
```

## Regras globais (valem para todo código deste repo)

- No cluster fly-det: GPU só via Slurm (`sbatch --partition=h100n2`), nunca no login node;
  submissão requer aprovação explícita. Instalação standalone local usa CPU e não exige Slurm.
- No cluster fly-det: dados, caches e checkpoints em `/raid/user_marcospaulo/`, nunca na home.
  Em outras instalações, configure `ANNOTATE_ROOT` para armazenamento persistente fora do Git.
- Nunca redimensionar imagens do dataset; thumbnails/tiles são derivados em cache.
- Escrita de `.txt`/`.json` de labels sempre atômica (tmp + rename).
- Classes de projeto: derivadas da fonte (checkpoint / digitação / arquivo de labels) e **append-only**.
- Split de dados sempre por placa/período, nunca aleatório por imagem.
- Nunca `git push` sem autorização explícita.

## Desenvolvimento (uv)

```bash
make install          # API + dev (sem torch)
make install-api      # + FastAPI
make install-engine   # API + dev + Ultralytics/Supervision/PyTorch CPU
make check            # ruff + pytest
```