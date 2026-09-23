"""Rotas de projetos: criar, listar, ler e atualizar (PATCH restrito)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from annotation_platform.contracts import classes as class_rules
from annotation_platform.contracts.common import utcnow_iso
from annotation_platform.contracts.project import PreannotationConfig, ProjectConfig, load_project
from annotation_platform.contracts.status import current_status

from .config import Settings
from .deps import (
    PROJECT_SUBDIRS,
    get_settings,
    load_cfg,
    project_root,
    projects_root,
    save_cfg,
)
from .security import verify_api_key

router = APIRouter(tags=["projects"], dependencies=[Depends(verify_api_key)])

SettingsDep = Annotated[Settings, Depends(get_settings)]


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    slug: str | None = None
    created_by: str = Field(default="api", min_length=1)
    classes: list[str] | None = None
    checkpoint: str | None = None
    image_width: int = Field(default=1920, gt=0)
    image_height: int = Field(default=1080, gt=0)


class ProjectPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    classes: list[str] | None = None
    checkpoint: str | None = None


def _load_model_names(checkpoint: str) -> list[str]:
    """Lê model.names de um checkpoint Ultralytics, ordenado por índice.

    Import local proposital: não puxar torch/ultralytics no import do módulo
    (a API roda em CPU; testes monkeypatcham esta função).
    """
    from ultralytics import YOLO

    names = YOLO(checkpoint).names
    if isinstance(names, dict):
        return [str(names[i]) for i in sorted(names)]
    return [str(n) for n in names]


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _status_counts(root) -> dict[str, int]:
    statuses = current_status(root / "meta" / "status.jsonl")
    return dict(Counter(ev.event for ev in statuses.values()))


def _n_images(root) -> int:
    active = root / "images" / "active"
    if not active.is_dir():
        return 0
    return sum(1 for p in active.iterdir() if p.is_file())


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, settings: SettingsDep) -> dict:
    """Cria a árvore de diretórios (seção 3) + project.yaml.

    Com checkpoint: classes vêm de model.names do .pt (nunca digitadas).
    Sem checkpoint: classes vêm do body.
    """
    slug = body.slug or _slugify(body.name)
    if body.checkpoint:
        try:
            names = _load_model_names(body.checkpoint)
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"falha ao ler checkpoint {body.checkpoint!r}: {exc}",
            ) from exc
        try:
            classes = class_rules.initial_classes_from_checkpoint(names)
        except class_rules.ClassListError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        preannotation = PreannotationConfig(enabled=True, checkpoint=body.checkpoint)
    else:
        if not body.classes:
            raise HTTPException(
                status_code=422, detail="classes são obrigatórias quando não há checkpoint"
            )
        classes = body.classes
        preannotation = PreannotationConfig(enabled=False)
    try:
        cfg = ProjectConfig(
            name=body.name,
            slug=slug,
            created_at=utcnow_iso(),
            created_by=body.created_by,
            classes=classes,
            image_width=body.image_width,
            image_height=body.image_height,
            preannotation=preannotation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"config inválida: {exc}") from exc
    root = projects_root(settings) / slug
    if root.exists():
        raise HTTPException(status_code=409, detail=f"projeto {slug!r} já existe")
    for sub in PROJECT_SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    save_cfg(root, cfg)
    return cfg.model_dump(mode="json")


@router.get("/projects")
def list_projects(settings: SettingsDep) -> dict:
    """Lista projetos com stats básicas (contagens por status)."""
    root = projects_root(settings)
    items: list[dict] = []
    if root.is_dir():
        for child in sorted(root.iterdir()):
            if not (child / "project.yaml").is_file():
                continue
            try:
                cfg = load_project(child / "project.yaml")
            except Exception:
                continue  # projeto quebrado não derruba a listagem
            items.append(
                {
                    "slug": cfg.slug,
                    "name": cfg.name,
                    "n_classes": len(cfg.classes),
                    "n_images": _n_images(child),
                    "status_counts": _status_counts(child),
                }
            )
    return {"projects": items}


@router.get("/projects/{slug}")
def get_project(slug: str, settings: SettingsDep) -> dict:
    root = project_root(settings, slug)
    cfg = load_cfg(root)
    return {
        "config": cfg.model_dump(mode="json"),
        "n_images": _n_images(root),
        "status_counts": _status_counts(root),
    }


@router.patch("/projects/{slug}")
def patch_project(slug: str, body: ProjectPatch, settings: SettingsDep) -> dict:
    """Atualiza project.yaml. Classes são append-only; troca de checkpoint
    exige model.names prefixo-compatível (409 em divergência)."""
    root = project_root(settings, slug)
    cfg = load_cfg(root)
    if body.name is not None:
        cfg.name = body.name
    if body.classes is not None:
        old = cfg.classes
        new = body.classes
        if len(new) < len(old) or new[: len(old)] != old:
            raise HTTPException(
                status_code=409,
                detail="classes são append-only: reordenar/renomear/remover é proibido",
            )
        try:
            for extra in new[len(old) :]:
                cfg.classes = class_rules.add_class(cfg.classes, extra)
        except class_rules.ClassListError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    if body.checkpoint is not None:
        try:
            names = _load_model_names(body.checkpoint)
        except Exception as exc:
            raise HTTPException(
                status_code=422, detail=f"falha ao ler checkpoint {body.checkpoint!r}: {exc}"
            ) from exc
        try:
            class_rules.check_checkpoint_compatible(names, cfg.classes)
        except class_rules.ClassListError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        cfg.preannotation.checkpoint = body.checkpoint
        cfg.preannotation.enabled = True
    save_cfg(root, cfg)
    return cfg.model_dump(mode="json")
