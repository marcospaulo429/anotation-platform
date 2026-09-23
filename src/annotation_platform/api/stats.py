"""Rota de stats: progresso, correction rate e cobertura de tiles."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from annotation_platform.contracts.common import read_jsonl
from annotation_platform.contracts.draft import DraftDoc
from annotation_platform.contracts.status import EventType, current_status

from .config import Settings
from .deps import get_settings, project_root
from .security import verify_api_key

router = APIRouter(tags=["stats"], dependencies=[Depends(verify_api_key)])

SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/projects/{slug}/stats")
def project_stats(slug: str, settings: SettingsDep) -> dict:
    """Progresso do projeto.

    - status_counts: último evento por imagem ativa.
    - correction_rate: média de edit_ops por caixa origin="model", calculada
      sobre os drafts já commitados (evento draft_committed).
    - tiles_seen_avg: média de len(tiles_seen) sobre todos os drafts.
    """
    root = project_root(settings, slug)
    active = root / "images" / "active"
    names = sorted(p.name for p in active.iterdir() if p.is_file()) if active.is_dir() else []
    status_path = root / "meta" / "status.jsonl"
    statuses = current_status(status_path)
    counts = Counter(statuses[name].event if name in statuses else "unlabeled" for name in names)
    committed_stems = {
        Path(rec["img"]).stem
        for rec in read_jsonl(status_path)
        if rec.get("event") == EventType.DRAFT_COMMITTED
    }
    model_ops = 0
    model_boxes = 0
    tiles_counts: list[int] = []
    drafts_dir = root / "labels" / "drafts"
    if drafts_dir.is_dir():
        for draft_path in sorted(drafts_dir.glob("*.json")):
            try:
                doc = DraftDoc.model_validate(json.loads(draft_path.read_text(encoding="utf-8")))
            except (ValidationError, json.JSONDecodeError):
                continue
            tiles_counts.append(len(doc.tiles_seen))
            if draft_path.stem not in committed_stems:
                continue
            for box in doc.boxes:
                if box.origin == "model":
                    model_boxes += 1
                    model_ops += len(box.edit_ops)
    return {
        "images": len(names),
        "status_counts": dict(counts),
        "drafts": len(tiles_counts),
        "correction_rate": (model_ops / model_boxes) if model_boxes else None,
        "model_boxes_reviewed": model_boxes,
        "tiles_seen_avg": (sum(tiles_counts) / len(tiles_counts)) if tiles_counts else None,
    }
