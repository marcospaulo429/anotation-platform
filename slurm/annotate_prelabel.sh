#!/usr/bin/env bash
# =============================================================================
# NUNCA submeter sem aprovação explícita do usuário.
#
# Template sbatch — pré-anotação em lote (Fase 0 da plataforma).
# Uso:
#   sbatch slurm/annotate_prelabel.sh /raid/user_marcospaulo/annotate/projects/<slug> \
#       [--images IMG_1.jpg IMG_2.jpg] [--force] [--user marcos]
#
# Idempotente: imagens já com labels/pre/<stem>.txt são puladas (a menos de
# --force), então re-submeter o mesmo comando continua de onde parou.
# =============================================================================
#SBATCH --job-name=annotate-prelabel
#SBATCH --partition=h100n2
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --signal=B:SIGUSR1@300
#SBATCH --output=slurm_logs/%x_%j.out
#SBATCH --error=slurm_logs/%x_%j.err

set -euo pipefail

CONTAINER="${CONTAINER:-/raid/user_marcospaulo/containers/flydet-train.sif}"

if [[ $# -lt 1 ]]; then
    echo "usage: sbatch annotate_prelabel.sh <project_root> [annotate-engine args...]" >&2
    exit 2
fi
PROJECT_ROOT="$1"
shift

mkdir -p slurm_logs

# 300s antes do fim da janela o Slurm envia SIGUSR1: só logamos — a saída é
# idempotente (skip de já pré-anotadas), basta re-submeter para continuar.
on_timeout() {
    echo "[WARN] SIGUSR1: fim de janela iminente ($(date))." >&2
    echo "[WARN] Re-submeta o mesmo comando; imagens já pré-anotadas serão puladas." >&2
}
trap on_timeout SIGUSR1

echo "=============================="
echo "Job:      ${SLURM_JOB_ID:-N/A} (${SLURM_JOB_NAME:-N/A})"
echo "Node:     ${SLURM_NODELIST:-N/A}"
echo "Projeto:  ${PROJECT_ROOT}"
echo "Container:${CONTAINER}"
echo "Início:   $(date)"
echo "=============================="

RUNNER="singularity"
if command -v apptainer >/dev/null 2>&1; then
    RUNNER="apptainer"
fi

exec "$RUNNER" exec --nv \
    --bind /raid/user_marcospaulo:/raid/user_marcospaulo \
    "$CONTAINER" \
    annotate-engine --project "$PROJECT_ROOT" "$@"
