"""Rotas de import/export — wrappers HTTP finos sobre dataset_ops.

A lógica real mora em annotation_platform.dataset_ops (interface congelada,
implementada pelo anno-data). Aqui: validação de slug, tradução de erros e
o evento `exported`. NotImplementedError -> 501.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from annotation_platform import dataset_ops
from annotation_platform.contracts.status import EventType

from .config import Settings
from .deps import get_settings, project_root, record_event
from .security import verify_api_key

router = APIRouter(tags=["import-export"], dependencies=[Depends(verify_api_key)])

SettingsDep = Annotated[Settings, Depends(get_settings)]


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    images_dir: str = Field(min_length=1)
    labels_dir: str = Field(min_length=1)
    copy_files: bool = Field(default=False, alias="copy")
    dry_run: bool = True
    user: str = Field(default="api", min_length=1)


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: str = Field(default="api", min_length=1)


@router.post("/projects/{slug}/import")
def import_labels(slug: str, body: ImportRequest, settings: SettingsDep) -> dict:
    """Importa imagens+labels YOLO. dry_run=true (default) só valida e reporta."""
    root = project_root(settings, slug)
    try:
        report = dataset_ops.import_dataset(
            root,
            Path(body.images_dir),
            Path(body.labels_dir),
            user=body.user,
            copy=body.copy_files,
            dry_run=body.dry_run,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return report.model_dump(mode="json")


@router.post("/projects/{slug}/export")
def export_snapshot(slug: str, body: ExportRequest, settings: SettingsDep) -> dict:
    """Congela exports/vN (split por placa) e retorna o manifest."""
    root = project_root(settings, slug)
    try:
        manifest = dataset_ops.export_dataset(root, user=body.user)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    record_event(root, "-", EventType.EXPORTED, body.user, version=manifest.version)
    return manifest.model_dump(mode="json")


@router.get("/projects/{slug}/exports")
def list_exports(slug: str, settings: SettingsDep) -> dict:
    """Lista exports/vN existentes com seus manifests."""
    root = project_root(settings, slug)
    exports_dir = root / "exports"
    items: list[dict] = []
    if exports_dir.is_dir():
        for version_dir in sorted(exports_dir.iterdir()):
            manifest_path = version_dir / "manifest.json"
            if not version_dir.is_dir() or not manifest_path.is_file():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            items.append({"version": version_dir.name, "manifest": manifest})
    return {"exports": items}
