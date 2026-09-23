"""Internal filesystem helpers shared by the dataset_ops importer and exporter."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def image_files(directory: Path) -> list[Path]:
    """Sorted image files (jpg/jpeg/png, case-insensitive) directly in ``directory``."""
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


def link_or_copy(src: Path, dst: Path, *, copy: bool = False) -> None:
    """Hardlink ``src`` to ``dst`` (images are never resized or re-encoded).

    Falls back to ``shutil.copy2`` when hardlinking fails (e.g. cross-device)
    or when ``copy=True``. An existing ``dst`` is left untouched so re-runs
    are idempotent.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    if copy:
        shutil.copy2(src, dst)
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)
