"""Rotas de jobs de pré-anotação.

Fase 1: POST /preannotate NÃO submete Slurm — apenas registra a solicitação
em meta/jobs/<uuid>.json com status "pending" (a submissão sbatch é
integração posterior, sempre com aprovação explícita do usuário).
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from annotation_platform.contracts.common import atomic_write_json, utcnow_iso

from .config import Settings
from .deps import get_settings, load_cfg, project_root, safe_img
from .security import verify_api_key

router = APIRouter(tags=["jobs"], dependencies=[Depends(verify_api_key)])

SettingsDep = Annotated[Settings, Depends(get_settings)]


class PreannotateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    images: list[str] | Literal["all"] = "all"
    user: str = Field(default="api", min_length=1)


def _active_images(root) -> list[str]:
    active = root / "images" / "active"
    if not active.is_dir():
        return []
    return sorted(p.name for p in active.iterdir() if p.is_file())


@router.post("/projects/{slug}/preannotate", status_code=202)
def request_preannotate(slug: str, body: PreannotateRequest, settings: SettingsDep) -> dict:
    """Registra um job de pré-anotação (status pending) e retorna 202."""
    root = project_root(settings, slug)
    cfg = load_cfg(root)
    available = set(_active_images(root))
    if body.images == "all":
        images = sorted(available)
    else:
        missing = [name for name in body.images if safe_img(name) not in available]
        if missing:
            raise HTTPException(
                status_code=404, detail=f"imagens não encontradas no projeto: {missing}"
            )
        images = body.images
    if not images:
        raise HTTPException(status_code=422, detail="nenhuma imagem para pré-anotar")
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "status": "pending",
        "created_at": utcnow_iso(),
        "user": body.user,
        "images": images,
        "params": cfg.preannotation.model_dump(mode="json"),
    }
    atomic_write_json(root / "meta" / "jobs" / f"{job_id}.json", job)
    return job


@router.get("/projects/{slug}/jobs")
def list_jobs(slug: str, settings: SettingsDep) -> dict:
    """Lista jobs registrados em meta/jobs/ (mais antigos primeiro)."""
    root = project_root(settings, slug)
    jobs_dir = root / "meta" / "jobs"
    items: list[dict] = []
    if jobs_dir.is_dir():
        for path in sorted(jobs_dir.glob("*.json")):
            try:
                items.append(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
    items.sort(key=lambda job: job.get("created_at", ""))
    return {"jobs": items}
