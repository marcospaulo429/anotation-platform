"""Batch pre-annotation orchestration (pure: NO torch/ultralytics imports).

Given a project root, iterate images from ``images/active/`` (or a sublist),
call an injected predictor and write, per image:

- ``labels/pre/<stem>.txt``       YOLO text, no confidence (contracts.yolo)
- ``labels/pre_meta/<stem>.json`` sidecar with conf + provenance (contracts.pre_meta)
- append ``prelabeled`` event to ``meta/status.jsonl`` (contracts.status)

Existing ``labels/pre/<stem>.txt`` are skipped by default (``force=True`` to
redo). All writes are atomic (contracts.common). Per-image confidence lives
only in the pre_meta sidecar — the .txt stays pure YOLO.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ..contracts.common import atomic_write_json, atomic_write_text, utcnow_iso
from ..contracts.pre_meta import EngineParams, ModelRef, PreBox, PreMeta
from ..contracts.project import PreannotationConfig, ProjectConfig, load_project
from ..contracts.status import EventType, StatusEvent, append_event
from ..contracts.yolo import YoloLine, dump_yolo_text
from .checkpoint import verified_checkpoint_sha256

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .predict import Predictor

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


@dataclass
class PrelabelSummary:
    """Result (or plan, when dry_run) of a pre-annotation batch."""

    processed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    dry_run: bool = False


def resolve_images(project_root: Path, images: Sequence[str] | None) -> list[Path]:
    """Image paths to process: explicit sublist (names in active/) or all of active/."""
    active = project_root / "images" / "active"
    if not active.is_dir():
        raise FileNotFoundError(f"active images dir not found: {active}")
    if images is None:
        return sorted(p for p in active.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    resolved: list[Path] = []
    for name in images:
        path = active / name
        if not path.is_file():
            raise FileNotFoundError(f"image not found in images/active/: {name}")
        resolved.append(path)
    return resolved


def _engine_params(cfg: PreannotationConfig) -> EngineParams:
    is_sahi = cfg.engine == "sahi"
    return EngineParams(
        imgsz=cfg.imgsz,
        conf=cfg.conf_threshold,
        iou=cfg.iou_threshold,
        slice=cfg.slice.size if is_sahi else None,
        overlap=cfg.slice.overlap if is_sahi else None,
    )


def _validate_boxes(boxes: list[PreBox], n_classes: int, image_name: str) -> None:
    for box in boxes:
        if box.cls >= n_classes:
            raise ValueError(
                f"{image_name}: predicted class {box.cls} out of range "
                f"(project has {n_classes} classes)"
            )


def preannotate_project(
    project_root: Path | str,
    predictor: Predictor | None,
    *,
    images: Sequence[str] | None = None,
    force: bool = False,
    user: str = "engine",
    dry_run: bool = False,
) -> PrelabelSummary:
    """Run (or plan, with dry_run=True) the pre-annotation batch for a project."""
    root = Path(project_root)
    cfg: ProjectConfig = load_project(root / "project.yaml")
    pre_cfg = cfg.preannotation
    status_path = root / "meta" / "status.jsonl"
    pre_dir = root / "labels" / "pre"
    meta_dir = root / "labels" / "pre_meta"

    todo: list[Path] = []
    summary = PrelabelSummary(dry_run=dry_run)
    for path in resolve_images(root, images):
        if (pre_dir / f"{path.stem}.txt").exists() and not force:
            summary.skipped.append(path.name)
        else:
            todo.append(path)

    if dry_run:
        summary.processed.extend(p.name for p in todo)
        return summary

    if predictor is None:
        raise ValueError("a predictor is required unless dry_run=True")
    if not pre_cfg.enabled:
        raise ValueError("preannotation.enabled=false in project.yaml")

    model_ref = ModelRef(
        checkpoint=pre_cfg.checkpoint or "",
        sha256=verified_checkpoint_sha256(pre_cfg),
        wandb_run=pre_cfg.wandb_run,
    )
    params = _engine_params(pre_cfg)
    n_classes = len(cfg.classes)

    for path in todo:
        started = time.perf_counter()
        try:
            boxes = list(predictor(path))
            _validate_boxes(boxes, n_classes, path.name)
        except Exception as exc:
            append_event(
                status_path,
                StatusEvent(
                    t=utcnow_iso(),
                    img=path.name,
                    event=EventType.PREANNOTATE_FAILED,
                    user=user,
                    error=f"{type(exc).__name__}: {exc}",
                ),
            )
            summary.failed[path.name] = str(exc)
            continue
        elapsed = time.perf_counter() - started

        yolo_lines = [YoloLine(cls=b.cls, cx=b.cx, cy=b.cy, w=b.w, h=b.h) for b in boxes]
        meta = PreMeta(
            image=path.name,
            created_at=utcnow_iso(),
            model=model_ref,
            engine=pre_cfg.engine,
            params=params,
            inference_seconds=round(elapsed, 3),
            boxes=boxes,
        )
        atomic_write_text(pre_dir / f"{path.stem}.txt", dump_yolo_text(yolo_lines))
        atomic_write_json(meta_dir / f"{path.stem}.json", meta.model_dump(mode="json"))
        append_event(
            status_path,
            StatusEvent(
                t=utcnow_iso(),
                img=path.name,
                event=EventType.PRELABELED,
                user=user,
                n_boxes=len(boxes),
                engine=pre_cfg.engine,
            ),
        )
        summary.processed.append(path.name)

    return summary
