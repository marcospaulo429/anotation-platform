"""Draft JSON contract (PREANNOTATION_PLATFORM.md section 4.2).

Drafts are the rich autosave format: per-box origin (model/human), model
confidence, edit ops and a bounded history. The YOLO .txt in labels/manual/ is
only written on commit — drafts never enter training exports.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = 1

# Edit operations tracked for correction-rate metrics and undo.
EditOp = Literal["create", "move", "resize", "relabel", "delete", "accept"]
# History também registra meta-ops de sessão (undo/redo não têm caixa própria).
HistoryOp = Literal["create", "move", "resize", "relabel", "delete", "accept", "undo", "redo"]


class DraftBox(BaseModel):
    """One bounding box inside a draft.

    Coordinates are YOLO-normalized: cx, cy in [0, 1]; w, h in (0, 1].
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, description="uuid-v4")
    cls: int = Field(ge=0)
    cx: float = Field(ge=0.0, le=1.0)
    cy: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)
    origin: Literal["model", "human"]
    model_conf: float | None = Field(default=None, ge=0.0, le=1.0)
    edited: bool = False
    edit_ops: list[EditOp] = Field(default_factory=list)

    @field_validator("model_conf")
    @classmethod
    def _conf_only_for_model(cls, v: float | None, info) -> float | None:
        # human-created boxes have no model confidence
        if info.data.get("origin") == "human" and v is not None:
            raise ValueError("model_conf is only meaningful for origin='model'")
        return v


class HistoryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    t: str
    op: HistoryOp
    box: str | None = Field(default=None, description="id da caixa afetada; None p/ undo/redo")


class DraftDoc(BaseModel):
    """labels/drafts/<img>.json — what autosave writes."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCHEMA_VERSION)
    image: str = Field(min_length=1)
    base_version: str = Field(
        min_length=1, description="sha256 of the loaded state; mismatch on save -> 409"
    )
    updated_at: str
    updated_by: str = Field(min_length=1)
    ops_since_commit: int = Field(default=0, ge=0)
    tiles_seen: list[int] = Field(default_factory=list)
    boxes: list[DraftBox] = Field(default_factory=list)
    history: list[HistoryEvent] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _known_schema(cls, v: int) -> int:
        if v != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {v}; expected {SCHEMA_VERSION}")
        return v

    @field_validator("tiles_seen")
    @classmethod
    def _tiles_non_negative(cls, v: list[int]) -> list[int]:
        if any(t < 0 for t in v):
            raise ValueError("tiles_seen must contain non-negative tile indices")
        return v
