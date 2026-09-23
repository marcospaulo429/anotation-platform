# anotation-platform

Plataforma de pré-anotação estilo Roboflow para datasets YOLO de armadilhas de moscas (fly-det).

Arquitetura, contratos e plano de orquestração: ver `PREANNOTATION_PLATFORM.md` no repositório pai
(`../PREANNOTATION_PLATFORM.md`). Este repo é um **submódulo** do fly-det.

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