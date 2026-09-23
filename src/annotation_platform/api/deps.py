"""Helpers compartilhados pelos routers: paths, validação, base_version, eventos."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from annotation_platform.contracts.common import atomic_write_text, utcnow_iso
from annotation_platform.contracts.project import ProjectConfig, dump_project, load_project
from annotation_platform.contracts.status import EventType, StatusEvent, append_event

from .config import Settings

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_IMG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Árvore de diretórios de um projeto (PREANNOTATION_PLATFORM.md seção 3).
PROJECT_SUBDIRS = (
    "images/incoming",
    "images/active",
    "labels/pre",
    "labels/pre_meta",
    "labels/drafts",
    "labels/manual",
    "labels/merged",
    "meta/jobs",
    "exports",
)


def get_settings(request: Request) -> Settings:
    """Dependência: settings guardados em app.state pela factory."""
    return request.app.state.settings


def projects_root(settings: Settings) -> Path:
    return settings.annotate_root / "projects"


def cache_root(settings: Settings) -> Path:
    """Cache derivado (thumbs/tiles), regenerável, fora dos projetos."""
    return settings.annotate_root / ".cache"


def project_root(settings: Settings, slug: str) -> Path:
    """Resolve o diretório do projeto; 404 em slug inválido ou inexistente."""
    if not _SLUG_RE.match(slug):
        raise HTTPException(status_code=404, detail=f"projeto {slug!r} não encontrado")
    root = projects_root(settings) / slug
    if not (root / "project.yaml").is_file():
        raise HTTPException(status_code=404, detail=f"projeto {slug!r} não encontrado")
    return root


def load_cfg(root: Path) -> ProjectConfig:
    try:
        return load_project(root / "project.yaml")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"project.yaml inválido: {exc}") from exc


def save_cfg(root: Path, cfg: ProjectConfig) -> None:
    """Reescreve project.yaml atomicamente (tmp + rename)."""
    atomic_write_text(root / "project.yaml", dump_project(cfg))


def safe_img(img: str) -> str:
    """Valida nome de imagem (sem path traversal)."""
    if not _IMG_RE.match(img):
        raise HTTPException(status_code=422, detail=f"nome de imagem inválido: {img!r}")
    return img


def active_image(root: Path, img: str) -> Path:
    """Resolve images/active/<img>; 404 se não existir."""
    safe_img(img)
    path = root / "images" / "active" / img
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"imagem {img!r} não encontrada no projeto")
    return path


def compute_base_version(root: Path, stem: str) -> str:
    """sha256 do estado atual de labels da imagem — contrato do autosave.

    O "estado carregado" é o conteúdo bruto de ``labels/manual/<stem>.txt`` se
    existir; senão ``labels/pre/<stem>.txt``; senão a string vazia. O cliente
    envia esse hash como ``base_version`` no PUT de draft e o servidor grava
    apenas se coincidir com o estado no momento do save (divergência -> 409).
    """
    for sub in ("manual", "pre"):
        path = root / "labels" / sub / f"{stem}.txt"
        if path.is_file():
            return hashlib.sha256(path.read_bytes()).hexdigest()
    return hashlib.sha256(b"").hexdigest()


def record_event(root: Path, img: str, event: EventType, user: str, **extra: Any) -> None:
    """Append de um evento em meta/status.jsonl (append-only, fsync)."""
    append_event(
        root / "meta" / "status.jsonl",
        StatusEvent(t=utcnow_iso(), img=img, event=event, user=user, **extra),
    )
