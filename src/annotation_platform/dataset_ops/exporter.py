"""Export an immutable training snapshot (exports/vN) from a project.

Contract (frozen by the orchestrator; implement below):

- Reads ONLY ``labels/manual/`` (+ explicitly accepted ``labels/pre/``);
  drafts NEVER enter training data.
- Split is ALWAYS by plate/period, never random per image. The default plate
  key is the filename stem up to the first ``_`` (the whole stem when there is
  no separator); callers may inject a custom key function.
- Writes ``exports/vN/`` with data.yaml (validated against project classes),
  manifest.json (counts per split, plate lists, hashes, strategy used) and
  images/{train,val,test}/ + labels/{train,val,test}/ (hardlinks).
- Snapshots are immutable: vN is monotonically increasing, never overwritten.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from annotation_platform.contracts.common import atomic_write_json, atomic_write_text, utcnow_iso
from annotation_platform.contracts.project import load_project
from annotation_platform.contracts.status import EventType, StatusEvent, append_event
from annotation_platform.contracts.yolo import YoloValidationError, parse_yolo_file, parse_yolo_text

from ._common import image_files, link_or_copy

DEFAULT_PLATE_KEY_RULE = "stem up to the first '_' (whole stem when there is no '_')"
CUSTOM_PLATE_KEY_RULE = "custom callable (receives the image filename)"


class SplitCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    images: int = Field(ge=0)
    boxes: int = Field(ge=0)
    plates: list[str] = Field(default_factory=list)


class ExportManifest(BaseModel):
    """Contents of exports/vN/manifest.json."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    created_at: str
    created_by: str
    split_strategy: str = "by_plate"
    plate_key_rule: str
    classes: list[str]
    train: SplitCounts
    val: SplitCounts
    test: SplitCounts


def export_dataset(
    project_root: Path,
    *,
    user: str,
    plate_key: Callable[[str], str] | None = None,
) -> ExportManifest:
    """Freeze an export snapshot of the project at ``project_root``.

    Args:
        project_root: project directory containing project.yaml.
        user: who is exporting (recorded in manifest and status events).
        plate_key: maps image filename -> plate id; None = default rule above.

    Returns:
        ExportManifest (also written to exports/vN/manifest.json).

    Raises:
        ValueError: no labeled images to export, a manual label fails
            validation, or the plate split would leave train empty. Any
            partial ``exports/vN`` directory is removed before re-raising.
    """
    project_root = Path(project_root)
    project = load_project(project_root / "project.yaml")
    n_classes = len(project.classes)
    key_rule = CUSTOM_PLATE_KEY_RULE if plate_key is not None else DEFAULT_PLATE_KEY_RULE

    # Collect labeled images: ONLY labels/manual/ counts — drafts NEVER enter.
    entries: dict[str, list[tuple[Path, Path, int]]] = {}  # plate -> [(image, label, n_boxes)]
    for image in image_files(project_root / "images" / "active"):
        label = project_root / "labels" / "manual" / f"{image.stem}.txt"
        if not label.exists():
            continue
        try:
            lines = parse_yolo_file(label, n_classes=n_classes)
        except YoloValidationError as exc:
            raise ValueError(f"invalid manual label {label.name}: {exc}") from exc
        plate = plate_key(image.name) if plate_key is not None else _default_plate_key(image.stem)
        entries.setdefault(plate, []).append((image, label, len(lines)))

    if not entries:
        raise ValueError("nothing to export: no images with labels/manual/*.txt")

    plates = sorted(entries)  # sorted for reproducibility
    train, val, test = _split_plates(
        plates, project.export.val_fraction, project.export.test_fraction
    )

    exports_dir = project_root / "exports"
    existing = [
        int(p.name[1:])
        for p in (exports_dir.glob("v*") if exports_dir.exists() else [])
        if p.is_dir() and p.name[1:].isdigit()
    ]
    version = max(existing, default=0) + 1
    out = exports_dir / f"v{version}"
    splits = {"train": train, "val": val, "test": test}

    try:
        for split, split_plates in splits.items():
            for plate in split_plates:
                for image, label, _n in entries[plate]:
                    link_or_copy(image, out / "images" / split / image.name)
                    link_or_copy(label, out / "labels" / split / label.name)

        # Final validation: every exported label line must be in range.
        for split in splits:
            for exported in sorted((out / "labels" / split).glob("*.txt")):
                try:
                    parse_yolo_text(exported.read_text(encoding="utf-8"), n_classes=n_classes)
                except YoloValidationError as exc:
                    raise ValueError(f"export validation failed on {exported.name}: {exc}") from exc

        data_yaml = {
            "path": str(out.relative_to(project_root)),
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "names": list(project.classes),
            "nc": n_classes,
        }
        atomic_write_text(
            out / "data.yaml", yaml.safe_dump(data_yaml, sort_keys=False, allow_unicode=True)
        )

        manifest = ExportManifest(
            version=version,
            created_at=utcnow_iso(),
            created_by=user,
            split_strategy=project.export.split_strategy,
            plate_key_rule=key_rule,
            classes=list(project.classes),
            train=_split_counts(train, entries),
            val=_split_counts(val, entries),
            test=_split_counts(test, entries),
        )
        atomic_write_json(out / "manifest.json", manifest.model_dump(mode="json"))
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)  # never leave a partial export behind
        raise

    counts = {
        split: {"images": c.images, "boxes": c.boxes}
        for split, c in (("train", manifest.train), ("val", manifest.val), ("test", manifest.test))
    }
    append_event(
        project_root / "meta" / "status.jsonl",
        StatusEvent(
            t=manifest.created_at,
            img="-",
            event=EventType.EXPORTED,
            user=user,
            version=version,
            counts=counts,
        ),
    )
    return manifest


def _default_plate_key(stem: str) -> str:
    return stem.split("_", 1)[0]


def _split_plates(
    plates: list[str], val_fraction: float, test_fraction: float
) -> tuple[list[str], list[str], list[str]]:
    """Deterministically split SORTED plates into (train, val, test).

    First ``n_test`` plates -> test, next ``n_val`` -> val, remainder -> train,
    with ``n_* = round(n_plates * fraction)`` (round-half-even; no RNG, fully
    reproducible). A plate never appears in two splits.
    """
    n = len(plates)
    n_test = round(n * test_fraction)
    n_val = round(n * val_fraction)
    if n - n_test - n_val < 1:
        raise ValueError(
            f"cannot split {n} plates with val_fraction={val_fraction} and "
            f"test_fraction={test_fraction}: train would be empty"
        )
    test = plates[:n_test]
    val = plates[n_test : n_test + n_val]
    train = plates[n_test + n_val :]
    return train, val, test


def _split_counts(
    split_plates: list[str], entries: dict[str, list[tuple[Path, Path, int]]]
) -> SplitCounts:
    images = sum(len(entries[p]) for p in split_plates)
    boxes = sum(n for p in split_plates for _img, _lbl, n in entries[p])
    return SplitCounts(images=images, boxes=boxes, plates=list(split_plates))
