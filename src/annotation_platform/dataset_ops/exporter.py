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

from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


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
        NotImplementedError: until anno-data implements this function.
    """
    raise NotImplementedError("anno-data: implement export_dataset")
