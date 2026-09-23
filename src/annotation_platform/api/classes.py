"""Rotas de classes de um projeto (append-only, congelado em 2026-09-23)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from annotation_platform.contracts import classes as class_rules
from annotation_platform.contracts.status import EventType

from .config import Settings
from .deps import get_settings, load_cfg, project_root, record_event, save_cfg
from .security import verify_api_key

router = APIRouter(tags=["classes"], dependencies=[Depends(verify_api_key)])

SettingsDep = Annotated[Settings, Depends(get_settings)]


class ClassAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    user: str = Field(default="api", min_length=1)


def _classes_payload(cfg) -> list[dict]:
    return [{"index": i, "name": name} for i, name in enumerate(cfg.classes)]


@router.get("/projects/{slug}/classes")
def list_classes(slug: str, settings: SettingsDep) -> dict:
    cfg = load_cfg(project_root(settings, slug))
    return {"classes": _classes_payload(cfg)}


@router.post("/projects/{slug}/classes", status_code=201)
def add_class(slug: str, body: ClassAdd, settings: SettingsDep) -> dict:
    """Adiciona classe NO FINAL da lista. Reordenar/remover não existe (409)."""
    root = project_root(settings, slug)
    cfg = load_cfg(root)
    try:
        cfg.classes = class_rules.add_class(cfg.classes, body.name)
    except class_rules.ClassListError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    save_cfg(root, cfg)
    # Evento por projeto (não por imagem): img="-" por convenção.
    record_event(
        root,
        "-",
        EventType.CLASS_ADDED,
        body.user,
        class_name=body.name.strip(),
        class_index=len(cfg.classes) - 1,
    )
    return {"classes": _classes_payload(cfg)}
