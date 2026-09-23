"""Pre-meta JSON contract (PREANNOTATION_PLATFORM.md section 4.3).

Sidecar for labels/pre/*.txt: the YOLO format has no room for confidence, so
per-box confidence, model provenance (checkpoint sha256, W&B run) and engine
parameters live here. Essential for auditing and dataset provenance.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = 1


class ModelRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    wandb_run: str | None = None


class EngineParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    imgsz: int = Field(gt=0)
    conf: float = Field(gt=0.0, lt=1.0)
    iou: float = Field(gt=0.0, lt=1.0)
    slice: int | None = Field(default=None, gt=0)
    overlap: float | None = Field(default=None, ge=0.0, lt=1.0)


class PreBox(BaseModel):
    """Model prediction: YOLO box + confidence."""

    model_config = ConfigDict(extra="forbid")

    cls: int = Field(ge=0)
    cx: float = Field(ge=0.0, le=1.0)
    cy: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)
    conf: float = Field(ge=0.0, le=1.0)


class PreMeta(BaseModel):
    """labels/pre_meta/<img>.json"""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCHEMA_VERSION)
    image: str = Field(min_length=1)
    created_at: str
    model: ModelRef
    engine: Literal["sahi", "plain"]
    params: EngineParams
    inference_seconds: float = Field(ge=0.0)
    boxes: list[PreBox] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _known_schema(cls, v: int) -> int:
        if v != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {v}; expected {SCHEMA_VERSION}")
        return v
