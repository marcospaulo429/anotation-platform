"""project.yaml contract (PREANNOTATION_PLATFORM.md section 4.1).

Classes are derived from the creation source (checkpoint model.names / manual
typing / imported label file) and are APPEND-ONLY afterwards: new classes may
only be added at the end, at any time; never reorder/rename/remove (that is a
silent YOLO index bug).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = 1

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class SliceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    size: int = Field(default=640, gt=0)
    overlap: float = Field(default=0.2, ge=0.0, lt=1.0)


class PreannotationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    checkpoint: str | None = None
    checkpoint_sha256: str | None = None
    wandb_run: str | None = None
    engine: Literal["sahi", "plain"] = "sahi"
    imgsz: int = Field(default=1920, gt=0)
    conf_threshold: float = Field(default=0.25, gt=0.0, lt=1.0)
    iou_threshold: float = Field(default=0.7, gt=0.0, lt=1.0)
    slice: SliceConfig = Field(default_factory=SliceConfig)

    @model_validator(mode="after")
    def _checkpoint_required_when_enabled(self) -> PreannotationConfig:
        if self.enabled and not self.checkpoint:
            raise ValueError("preannotation.enabled=true requires a checkpoint path")
        return self


class AutosaveConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    every_n_ops: int = Field(default=5, gt=0)
    every_seconds: int = Field(default=30, gt=0)
    on_navigate: bool = True
    on_tab_hide: bool = True


class ExportConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    split_strategy: Literal["by_plate"] = "by_plate"  # NEVER random per image
    val_fraction: float = Field(default=0.15, gt=0.0, lt=1.0)
    test_fraction: float = Field(default=0.10, gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def _fractions_leave_train(self) -> ExportConfig:
        if self.val_fraction + self.test_fraction >= 1.0:
            raise ValueError("val_fraction + test_fraction must be < 1.0")
        return self


class ProjectConfig(BaseModel):
    """Root contract of a project (project.yaml)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCHEMA_VERSION)
    name: str = Field(min_length=1)
    slug: str
    created_at: str
    created_by: str = Field(min_length=1)
    classes: list[str] = Field(min_length=1)
    image_width: int = Field(default=1920, gt=0)
    image_height: int = Field(default=1080, gt=0)
    preannotation: PreannotationConfig = Field(default_factory=PreannotationConfig)
    autosave: AutosaveConfig = Field(default_factory=AutosaveConfig)
    export: ExportConfig = Field(default_factory=ExportConfig)

    @field_validator("schema_version")
    @classmethod
    def _known_schema(cls, v: int) -> int:
        if v != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {v}; expected {SCHEMA_VERSION}")
        return v

    @field_validator("slug")
    @classmethod
    def _slug_format(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(f"invalid slug {v!r}: use lowercase letters, digits and '-'")
        return v

    @field_validator("classes")
    @classmethod
    def _classes_sane(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("classes contain duplicates")
        for name in v:
            if not name or not name.strip():
                raise ValueError("class names must be non-empty")
        return v


def load_project(path: Path | str) -> ProjectConfig:
    """Load and validate a project.yaml."""
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return ProjectConfig.model_validate(data)


def dump_project(config: ProjectConfig) -> str:
    """Serialize a project config to YAML text (stable key order)."""
    return yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False, allow_unicode=True)
