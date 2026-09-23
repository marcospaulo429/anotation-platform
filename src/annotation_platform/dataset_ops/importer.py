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
        ImportReport with counts and per-file validation errors.

    Raises:
        NotImplementedError: until anno-data implements this function.
    """
    raise NotImplementedError("anno-data: implement import_dataset")
