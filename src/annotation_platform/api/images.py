"""Rotas de imagens: upload validado, listagem paginada, thumb/tiles/full.

Imagens do dataset NUNCA são redimensionadas: thumbnails e tiles são
derivados em cache sob <annotate_root>/.cache/ (regenerável).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from annotation_platform.contracts.status import EventType, current_status

from .config import Settings
from .deps import (
    active_image,
    cache_root,
    get_settings,
    load_cfg,
    project_root,
    record_event,
    safe_img,
)
from .security import verify_api_key, verify_api_key_or_query

router = APIRouter(tags=["images"], dependencies=[Depends(verify_api_key)])
# Rotas GET de mídia (thumb/tiles/full): <img> e o loader de tiles do canvas
# não enviam headers — aceitam ?api_key= via verify_api_key_or_query.
media_router = APIRouter(tags=["images"], dependencies=[Depends(verify_api_key_or_query)])

SettingsDep = Annotated[Settings, Depends(get_settings)]

ALLOWED_EXT = {".jpg", ".jpeg", ".png"}
ALLOWED_FORMATS = {"JPEG", "PNG"}
CHUNK_SIZE = 1 << 20  # 1 MiB
THUMB_SIZE = 320


async def _ingest_one(root: Path, cfg, upload: UploadFile, user: str) -> dict:
    """Ingere UM arquivo: incoming/ -> valida -> active/ + evento uploaded.

    Validação: extensão jpg/jpeg/png, formato real via Pillow e dimensões
    exatamente image_width x image_height do projeto.
    """
    name = Path(upload.filename or "").name
    safe_img(name)
    if Path(name).suffix.lower() not in ALLOWED_EXT:
        raise HTTPException(
            status_code=422, detail=f"extensão não suportada em {name!r} (use jpg/jpeg/png)"
        )
    incoming = root / "images" / "incoming" / name
    with open(incoming, "wb") as fh:
        while chunk := await upload.read(CHUNK_SIZE):
            fh.write(chunk)
    try:
        with Image.open(incoming) as im:
            fmt, width, height = im.format, im.size[0], im.size[1]
    except (UnidentifiedImageError, OSError) as exc:
        incoming.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="arquivo não é uma imagem válida") from exc
    if fmt not in ALLOWED_FORMATS:
        incoming.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"formato {fmt!r} não suportado")
    if (width, height) != (cfg.image_width, cfg.image_height):
        incoming.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail=(
                f"dimensões {width}x{height} divergem do projeto "
                f"({cfg.image_width}x{cfg.image_height})"
            ),
        )
    dest = root / "images" / "active" / name
    if dest.exists():
        incoming.unlink(missing_ok=True)
        raise HTTPException(
            status_code=409,
            detail=(
                f"{name!r} já existe no projeto; reenviar substituiria a imagem "
                "e deixaria labels da foto anterior órfãs. Renomeie o arquivo."
            ),
        )
    os.replace(incoming, dest)
    record_event(root, name, EventType.UPLOADED, user)
    return {"image": name, "status": "uploaded", "width": width, "height": height}


@router.post("/projects/{slug}/images", status_code=201)
async def upload_images(
    slug: str,
    settings: SettingsDep,
    files: Annotated[list[UploadFile], File()],
    user: str = "api",
) -> dict:
    """Upload multipart chunked de um ou mais arquivos (campo ``files``).

    Cada arquivo é validado isoladamente: falhas não abortam o lote —
    entram no relatório ``errors`` e o arquivo inválido é descartado.
    """
    root = project_root(settings, slug)
    cfg = load_cfg(root)
    uploaded: list[dict] = []
    errors: list[dict] = []
    for upload in files:
        try:
            uploaded.append(await _ingest_one(root, cfg, upload, user))
        except HTTPException as exc:
            errors.append({"file": upload.filename, "detail": exc.detail})
    return {"uploaded": uploaded, "errors": errors}


@router.get("/projects/{slug}/images")
def list_images(
    slug: str,
    settings: SettingsDep,
    status: str | None = None,
    cursor: Annotated[int, Query(ge=0)] = 0,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    """Lista paginada por cursor (índice) com status corrente por imagem."""
    root = project_root(settings, slug)
    active = root / "images" / "active"
    names = sorted(p.name for p in active.iterdir() if p.is_file()) if active.is_dir() else []
    statuses = current_status(root / "meta" / "status.jsonl")
    items = [_image_item(name, statuses) for name in names]
    if status is not None:
        items = [
            item for item in items if item["display_status"] == status or item["status"] == status
        ]
    page = items[cursor : cursor + page_size]
    next_cursor = cursor + page_size if cursor + page_size < len(items) else None
    return {"items": page, "next_cursor": next_cursor, "total": len(items)}


# Evento cru (status.jsonl) -> estado visual do strip de thumbs (seção 8 do MD).
_DISPLAY_STATUS = {
    "uploaded": "unlabeled",
    "imported": "done",
    "prelabeled": "prelabeled",
    "preannotate_failed": "unlabeled",
    "draft_saved": "draft",
    "draft_committed": "done",
    "done": "done",
    "reopened": "prelabeled",
    "reverted": "prelabeled",
}


def _image_item(name: str, statuses) -> dict:
    if name in statuses:
        raw = statuses[name].event
        return {"img": name, "status": raw, "display_status": _DISPLAY_STATUS.get(raw, "unlabeled")}
    return {"img": name, "status": "unlabeled", "display_status": "unlabeled"}


@media_router.get("/projects/{slug}/images/{img}/thumb")
def get_thumb(slug: str, img: str, settings: SettingsDep) -> FileResponse:
    """Thumbnail 320px cacheado em .cache/thumbs/<slug>/ (derivado, JPEG)."""
    root = project_root(settings, slug)
    src = active_image(root, img)
    cache_dir = cache_root(settings) / "thumbs" / slug
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / f"{Path(img).stem}.jpg"
    if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
        with Image.open(src) as im:
            thumb = im.convert("RGB")
            thumb.thumbnail((THUMB_SIZE, THUMB_SIZE))
            thumb.save(dest, "JPEG")
    return FileResponse(dest, media_type="image/jpeg")


@media_router.get("/projects/{slug}/images/{img}/tiles/{x}/{y}")
def get_tile(
    slug: str,
    img: str,
    x: int,
    y: int,
    settings: SettingsDep,
    w: Annotated[int, Query(gt=0, le=4096)] = 640,
) -> FileResponse:
    """Tile em resolução NATIVA (crop sem resize), cacheado em .cache/tiles/."""
    if x < 0 or y < 0:
        raise HTTPException(status_code=422, detail="coordenadas de tile devem ser >= 0")
    root = project_root(settings, slug)
    src = active_image(root, img)
    cache_dir = cache_root(settings) / "tiles" / slug / Path(img).stem / str(w)
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / f"{x}_{y}.jpg"
    if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
        with Image.open(src) as im:
            width, height = im.size
            if x * w >= width or y * w >= height:
                raise HTTPException(
                    status_code=404, detail=f"tile ({x},{y}) fora da imagem {width}x{height}"
                )
            box = (x * w, y * w, min((x + 1) * w, width), min((y + 1) * w, height))
            im.crop(box).convert("RGB").save(dest, "JPEG")
    return FileResponse(dest, media_type="image/jpeg")


@media_router.get("/projects/{slug}/images/{img}/full")
def get_full(slug: str, img: str, settings: SettingsDep) -> FileResponse:
    """Imagem original (streaming; nunca redimensionada)."""
    root = project_root(settings, slug)
    return FileResponse(active_image(root, img))
