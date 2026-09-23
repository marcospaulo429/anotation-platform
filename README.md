# anotation-platform

Plataforma de pré-anotação estilo Roboflow para datasets YOLO de armadilhas de moscas (fly-det).

Arquitetura, contratos e plano de orquestração: ver `PREANNOTATION_PLATFORM.md` no repositório pai
(`../PREANNOTATION_PLATFORM.md`). Este repo é um **submódulo** do fly-det.

---

## Rodando pela primeira vez

### Pré-requisitos
- Linux com **Python 3.12+** e [**uv**](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`).
- Um navegador moderno (Chrome/Firefox).
- (Opcional, para pré-anotação) um checkpoint YOLO `.pt` — ex.: `../epoch91.pt`.

### 1. Instalar

```bash
cd anotation-platform
make install-api        # API + dev (rápido). Engine (torch/SAHI) é opcional: make install-engine
```

### 2. Subir a plataforma (API + interface juntas)

```bash
API_KEY=minha-chave ANNOTATE_ROOT=$PWD/.data uv run --no-sync annotate-api
```

- `API_KEY` — a senha da plataforma (a interface vai pedir na 1ª vez).
- `ANNOTATE_ROOT` — onde ficam os projetos/dados (padrão: `/raid/user_marcospaulo/annotate`).
- A **interface web já é servida pela própria API** — não precisa de servidor separado.

Abra **http://localhost:5200/** → informe a chave → pronto.

> **Dica (dev):** se algo parecer não atualizar após editar código, force **Ctrl+Shift+R** (o navegador cacheia módulos).

### 3. Criar o primeiro projeto

Clique **+ Novo projeto** e siga o wizard de 3 passos:

1. **Nome** — o slug é gerado automaticamente.
2. **Caminho dos dados** — escolha um:
   - **Pré-anotar com modelo** → aponte um `.pt`; as **classes vêm do checkpoint** (você não digita nada).
   - **Manual do zero** → você define as classes (ordem = índice YOLO).
   - **Importar dados já anotados** → imagens + `.txt` YOLO existentes viram a base.
3. **Config** — thresholds da pré-anotação (se houver). **Criar projeto.**

### 4. Subir imagens e pré-anotar

- Aba **Imagens** → arraste os JPGs (1920×1080). 
- Botão **Pré-anotar** → registra o job. *A submissão ao cluster (Slurm/GPU) é manual/aprovada — nunca automática.*
- Para pré-anotar localmente em CPU (teste), rode no terminal:
  ```bash
  uv run --no-sync annotate-engine --project $ANNOTATE_ROOT/projects/<slug>
  ```

### 5. Anotar (a tela principal)

Aba **Anotar**. A imagem abre em **resolução nativa** (nunca encolhida). Caixas tracejadas = sugestão do modelo.

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

Aba **Importar/Exportar** → **Exportar** → gera `exports/v1/` com `data.yaml` e **split por placa** (nunca aleatório por imagem). Aponte esse export no treino do fly-det.

---

## Comandos de referência

```bash
make install-api      # instala API + dev
make install-engine   # + engine (torch/SAHI) — necessário p/ pré-anotar
make check            # ruff + pytest (172 testes)

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
docker/           # Compose do serviço (atrás do nginx do fly_det_api)
tests/            # Contratos automatizados (pytest)
```

## Regras globais (valem para todo código deste repo)

- GPU só via Slurm (`sbatch --partition=h100n2`). Nunca GPU no login node. Nunca submeter job sem aprovação explícita.
- Dados, caches e checkpoints em `/raid/user_marcospaulo/` (nunca na home). Dados da plataforma em `/raid/user_marcospaulo/annotate/` (fora do git).
- Nunca redimensionar imagens do dataset; thumbnails/tiles são derivados em cache.
- Escrita de `.txt`/`.json` de labels sempre atômica (tmp + rename).
- Classes de projeto: derivadas da fonte (checkpoint / digitação / arquivo de labels) e **append-only**.
- Split de dados sempre por placa/período, nunca aleatório por imagem.
- Nunca `git push` sem autorização explícita.

## Desenvolvimento (uv)

```bash
make install          # core + dev (rápido, sem torch)
make install-api      # + FastAPI
make install-engine   # + fly-det editável + ultralytics/torch (pesado)
make check            # ruff + pytest
```