"""Import an already-annotated YOLO dataset into a platform project.

Contract (frozen by the orchestrator; implement below):

- Images land in ``images/active/`` (never resized; hardlink by default,
  copy optional).
- Valid labels go STRAIGHT to ``labels/manual/`` (they are human-made ground
  truth by definition) and the image enters as ``done`` via an ``imported``
  event in ``meta/status.jsonl``.
- Images without a label file enter as ``unlabeled`` (event ``uploaded``).
- Validation BEFORE writing anything (dry-run): every label line must pass
  ``contracts.yolo`` with ``n_classes`` = project classes; the report lists
  per-file errors and the caller decides: import only the valid ones or abort.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from annotation_platform.contracts.common import atomic_write_text, utcnow_iso
from annotation_platform.contracts.project import load_project
from annotation_platform.contracts.status import EventType, StatusEvent, append_event
from annotation_platform.contracts.yolo import (
    YoloLine,
    YoloValidationError,
    dump_yolo_text,
    parse_yolo_file,
)

from ._common import image_files, link_or_copy


class FileImportError(BaseModel):
    """One file that failed validation during import."""

    model_config = ConfigDict(extra="forbid")

    file: str
    line: int | None = None
    message: str


class ImportReport(BaseModel):
    """Result of an import (or import dry-run)."""

    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True
    images_total: int = Field(ge=0, default=0)
    images_imported: int = Field(ge=0, default=0)
    images_without_label: int = Field(ge=0, default=0)
    boxes_total: int = Field(ge=0, default=0)
    errors: list[FileImportError] = Field(default_factory=list)


def import_dataset(
    project_root: Path,
    images_dir: Path,
    labels_dir: Path,
    *,
    user: str,
    copy: bool = False,
    dry_run: bool = True,
) -> ImportReport:
    """Import images+labels into the project at ``project_root``.

    Args:
        project_root: project directory containing project.yaml.
        images_dir: directory with source images.
        labels_dir: directory with YOLO .txt labels (same stems as images).
        user: who is importing (recorded in status events).
        copy: copy images instead of hardlinking.
        dry_run: validate only; write nothing.

    Returns:
        ImportReport with counts and per-file validation errors. In dry-run
        mode, counts describe what WOULD be imported.

    Raises:
        FileNotFoundError: if project.yaml or the source dirs do not exist.
    """
    project_root = Path(project_root)
    images_dir = Path(images_dir)
    labels_dir = Path(labels_dir)
    project = load_project(project_root / "project.yaml")
    n_classes = len(project.classes)

    report = ImportReport(dry_run=dry_run)

    # Pass 1 — validate EVERYTHING before writing anything.
    plan: list[tuple[Path, list[YoloLine] | None]] = []  # (image, lines | None=no label)
    for image in image_files(images_dir):
        report.images_total += 1
        label_path = labels_dir / f"{image.stem}.txt"
        if not label_path.exists():
            plan.append((image, None))
            report.images_without_label += 1
            continue
        try:
            lines = parse_yolo_file(label_path, n_classes=n_classes)
        except YoloValidationError as exc:
            report.errors.append(
                FileImportError(file=label_path.name, line=exc.line_no, message=str(exc))
            )
            continue
        except OSError as exc:
            report.errors.append(
                FileImportError(file=label_path.name, message=f"unreadable label: {exc}")
            )
            continue
        plan.append((image, lines))
        report.images_imported += 1
        report.boxes_total += len(lines)

    if dry_run:
        return report

    # Pass 2 — writes (images hardlinked, labels canonicalized, events appended).
    active_dir = project_root / "images" / "active"
    manual_dir = project_root / "labels" / "manual"
    status_path = project_root / "meta" / "status.jsonl"
    for image, lines in plan:
        link_or_copy(image, active_dir / image.name, copy=copy)
        if lines is None:
            append_event(
                status_path,
                StatusEvent(t=utcnow_iso(), img=image.name, event=EventType.UPLOADED, user=user),
            )
        else:
            atomic_write_text(manual_dir / f"{image.stem}.txt", dump_yolo_text(lines))
            append_event(
                status_path,
                StatusEvent(
                    t=utcnow_iso(),
                    img=image.name,
                    event=EventType.IMPORTED,
                    user=user,
                    n_boxes=len(lines),
                ),
            )
    return report
