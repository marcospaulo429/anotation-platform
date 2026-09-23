"""Rotas de labels: leitura (merged/manual/pre/draft), autosave, commit, revert."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from annotation_platform.contracts.common import atomic_write_json, atomic_write_text, utcnow_iso
from annotation_platform.contracts.draft import DraftBox, DraftDoc
from annotation_platform.contracts.pre_meta import PreMeta
from annotation_platform.contracts.status import EventType
from annotation_platform.contracts.yolo import (
    YoloLine,
    YoloValidationError,
    dump_yolo_text,
    parse_yolo_text,
)

from .config import Settings
from .deps import (
    active_image,
    compute_base_version,
    get_settings,
    load_cfg,
    project_root,
    record_event,
)
from .security import verify_api_key

router = APIRouter(tags=["labels"], dependencies=[Depends(verify_api_key)])

SettingsDep = Annotated[Settings, Depends(get_settings)]

LabelSource = Literal["merged", "manual", "pre", "draft"]


def _label_path(root: Path, sub: str, stem: str) -> Path:
    return root / "labels" / sub / f"{stem}.txt"


def _parse_label_file(root: Path, sub: str, stem: str, n_classes: int) -> list[YoloLine] | None:
    path = _label_path(root, sub, stem)
    if not path.is_file():
        return None
    try:
        return parse_yolo_text(path.read_text(encoding="utf-8"), n_classes=n_classes)
    except YoloValidationError as exc:
        raise HTTPException(
            status_code=500, detail=f"label {sub}/{stem}.txt inválido: {exc}"
        ) from exc


def _pre_confs(root: Path, stem: str) -> list[float | None]:
    """Confianças por caixa vindas de pre_meta/<stem>.json (alinhadas por índice)."""
    meta_path = root / "labels" / "pre_meta" / f"{stem}.json"
    if not meta_path.is_file():
        return []
    try:
        meta = PreMeta.model_validate(json.loads(meta_path.read_text(encoding="utf-8")))
    except (ValidationError, json.JSONDecodeError):
        return []
    return [box.conf for box in meta.boxes]


def _check_cls_range(doc: DraftDoc, n_classes: int) -> None:
    bad = sorted({b.cls for b in doc.boxes if b.cls >= n_classes})
    if bad:
        raise HTTPException(
            status_code=422,
            detail=f"ids de classe fora de faixa: {bad} (projeto tem {n_classes} classes)",
        )


@router.get("/projects/{slug}/labels/{img}")
def get_labels(
    slug: str,
    img: str,
    settings: SettingsDep,
    source: LabelSource = "merged",
) -> dict:
    """Lê anotações. merged = manual se existe, senão pre."""
    root = project_root(settings, slug)
    active_image(root, img)
    cfg = load_cfg(root)
    stem = Path(img).stem
    if source == "draft":
        draft_path = root / "labels" / "drafts" / f"{stem}.json"
        if not draft_path.is_file():
            raise HTTPException(status_code=404, detail=f"sem draft para {img!r}")
        try:
            doc = DraftDoc.model_validate(json.loads(draft_path.read_text(encoding="utf-8")))
        except (ValidationError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=500, detail=f"draft {stem}.json inválido: {exc}"
            ) from exc
        return doc.model_dump(mode="json")
    sub = source
    if source == "merged":
        sub = "manual" if _label_path(root, "manual", stem).is_file() else "pre"
    lines = _parse_label_file(root, sub, stem, len(cfg.classes))
    if lines is None:
        if source == "merged":
            return {
                "image": img,
                "source": "none",
                "base_version": compute_base_version(root, stem),
                "n_boxes": 0,
                "boxes": [],
            }
        raise HTTPException(status_code=404, detail=f"sem labels {sub} para {img!r}")
    confs = _pre_confs(root, stem) if sub == "pre" else []
    boxes = []
    for idx, line in enumerate(lines):
        box = {"cls": line.cls, "cx": line.cx, "cy": line.cy, "w": line.w, "h": line.h}
        if idx < len(confs):
            box["conf"] = confs[idx]
        boxes.append(box)
    return {
        "image": img,
        "source": sub,
        "base_version": compute_base_version(root, stem),
        "n_boxes": len(boxes),
        "boxes": boxes,
    }


@router.put("/projects/{slug}/labels/{img}/draft")
def put_draft(slug: str, img: str, doc: DraftDoc, settings: SettingsDep) -> dict:
    """Autosave: grava drafts/<stem>.json atomicamente.

    Exige base_version == sha256 do estado atual (manual > pre > vazio);
    divergência -> 409 (last-writer-wins com aviso no cliente).
    """
    root = project_root(settings, slug)
    active_image(root, img)
    cfg = load_cfg(root)
    stem = Path(img).stem
    if doc.image != img:
        raise HTTPException(
            status_code=422, detail=f"draft.image {doc.image!r} != imagem da rota {img!r}"
        )
    _check_cls_range(doc, len(cfg.classes))
    current = compute_base_version(root, stem)
    if doc.base_version != current:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "base_version divergente: o estado mudou desde o carregamento",
                "current_base_version": current,
            },
        )
    atomic_write_json(root / "labels" / "drafts" / f"{stem}.json", doc.model_dump(mode="json"))
    record_event(
        root,
        img,
        EventType.DRAFT_SAVED,
        doc.updated_by,
        ops=doc.ops_since_commit,
        n_boxes=len(doc.boxes),
    )
    return {"status": "saved", "image": img, "n_boxes": len(doc.boxes)}


@router.post("/projects/{slug}/labels/{img}/commit")
def commit_draft(
    slug: str,
    img: str,
    settings: SettingsDep,
    user: Annotated[str | None, Query()] = None,
) -> dict:
    """Commit: draft -> labels/manual/<stem>.txt (atômico) + eventos."""
    root = project_root(settings, slug)
    active_image(root, img)
    cfg = load_cfg(root)
    stem = Path(img).stem
    draft_path = root / "labels" / "drafts" / f"{stem}.json"
    if not draft_path.is_file():
        raise HTTPException(status_code=404, detail=f"sem draft para commitar em {img!r}")
    try:
        doc = DraftDoc.model_validate(json.loads(draft_path.read_text(encoding="utf-8")))
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"draft {stem}.json inválido: {exc}") from exc
    _check_cls_range(doc, len(cfg.classes))
    lines = [YoloLine(cls=b.cls, cx=b.cx, cy=b.cy, w=b.w, h=b.h) for b in doc.boxes]
    atomic_write_text(_label_path(root, "manual", stem), dump_yolo_text(lines))
    who = user or doc.updated_by
    record_event(
        root, img, EventType.DRAFT_COMMITTED, who, ops=doc.ops_since_commit, n_boxes=len(lines)
    )
    record_event(root, img, EventType.DONE, who, n_boxes=len(lines))
    return {"status": "done", "image": img, "n_boxes": len(lines)}


@router.post("/projects/{slug}/labels/{img}/revert")
def revert_draft(
    slug: str,
    img: str,
    settings: SettingsDep,
    to: Literal["pre"] = "pre",
    user: str = "api",
) -> dict:
    """Recria o draft a partir de pre/ + pre_meta/ (caixas origin="model").

    O base_version do novo draft é o sha256 do conteúdo de pre/ (o estado
    carregado após o revert). labels/manual/ NÃO é apagado aqui.
    """
    root = project_root(settings, slug)
    active_image(root, img)
    cfg = load_cfg(root)
    stem = Path(img).stem
    pre_path = _label_path(root, to, stem)
    if not pre_path.is_file():
        raise HTTPException(status_code=404, detail=f"sem pré-anotação para {img!r}")
    text = pre_path.read_text(encoding="utf-8")
    try:
        lines = parse_yolo_text(text, n_classes=len(cfg.classes))
    except YoloValidationError as exc:
        raise HTTPException(
            status_code=500, detail=f"label pre/{stem}.txt inválido: {exc}"
        ) from exc
    confs = _pre_confs(root, stem)
    boxes = [
        DraftBox(
            id=str(uuid.uuid4()),
            cls=line.cls,
            cx=line.cx,
            cy=line.cy,
            w=line.w,
            h=line.h,
            origin="model",
            model_conf=confs[idx] if idx < len(confs) else None,
            edited=False,
        )
        for idx, line in enumerate(lines)
    ]
    doc = DraftDoc(
        image=img,
        base_version=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        updated_at=utcnow_iso(),
        updated_by=user,
        boxes=boxes,
    )
    atomic_write_json(root / "labels" / "drafts" / f"{stem}.json", doc.model_dump(mode="json"))
    record_event(root, img, EventType.REVERTED, user, to=to)
    return doc.model_dump(mode="json")
