"""Contract tests for project.yaml (PREANNOTATION_PLATFORM.md section 4.1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from annotation_platform.contracts.project import (
    ExportConfig,
    PreannotationConfig,
    ProjectConfig,
    dump_project,
    load_project,
)

# Literal example from PREANNOTATION_PLATFORM.md section 4.1
PROJECT_YAML_EXAMPLE = """\
schema_version: 1
name: Placas 2026 Q4
slug: placas-2026-q4
created_at: "2026-09-23T14:00:00"
created_by: marcos
classes: [MD, MV, MC, MF, INS, NOISE, MAR]
image_width: 1920
image_height: 1080
preannotation:
  enabled: true
  checkpoint: /raid/user_marcospaulo/models/e0_yolo26m_baseline_best.pt
  checkpoint_sha256: "abc123"
  wandb_run: "pestline/fly-det/036ef018"
  engine: sahi
  imgsz: 1920
  conf_threshold: 0.25
  iou_threshold: 0.7
  slice: { size: 640, overlap: 0.2 }
autosave:
  every_n_ops: 5
  every_seconds: 30
  on_navigate: true
  on_tab_hide: true
export:
  split_strategy: by_plate
  val_fraction: 0.15
  test_fraction: 0.10
"""


def _example() -> ProjectConfig:
    import yaml

    return ProjectConfig.model_validate(yaml.safe_load(PROJECT_YAML_EXAMPLE))


def test_md_example_is_valid() -> None:
    cfg = _example()
    assert cfg.slug == "placas-2026-q4"
    assert cfg.classes == ["MD", "MV", "MC", "MF", "INS", "NOISE", "MAR"]
    assert cfg.preannotation.engine == "sahi"
    assert cfg.preannotation.slice.size == 640
    assert cfg.export.split_strategy == "by_plate"


def test_yaml_roundtrip(tmp_path) -> None:
    cfg = _example()
    path = tmp_path / "project.yaml"
    path.write_text(dump_project(cfg), encoding="utf-8")
    assert load_project(path) == cfg


def test_slug_must_be_kebab_case() -> None:
    cfg = _example().model_dump()
    cfg["slug"] = "Placas Q4!"
    with pytest.raises(ValidationError, match="invalid slug"):
        ProjectConfig.model_validate(cfg)


def test_classes_reject_duplicates_and_empty() -> None:
    cfg = _example().model_dump()
    cfg["classes"] = ["MD", "MD"]
    with pytest.raises(ValidationError, match="duplicates"):
        ProjectConfig.model_validate(cfg)
    cfg["classes"] = ["MD", "  "]
    with pytest.raises(ValidationError, match="non-empty"):
        ProjectConfig.model_validate(cfg)


def test_classes_required_nonempty() -> None:
    cfg = _example().model_dump()
    cfg["classes"] = []
    with pytest.raises(ValidationError):
        ProjectConfig.model_validate(cfg)


def test_unknown_schema_version_rejected() -> None:
    cfg = _example().model_dump()
    cfg["schema_version"] = 99
    with pytest.raises(ValidationError, match="schema_version"):
        ProjectConfig.model_validate(cfg)


def test_thresholds_bounded() -> None:
    with pytest.raises(ValidationError):
        PreannotationConfig(enabled=False, conf_threshold=1.5)
    with pytest.raises(ValidationError):
        PreannotationConfig(enabled=False, iou_threshold=0.0)


def test_enabled_preannotation_requires_checkpoint() -> None:
    with pytest.raises(ValidationError, match="checkpoint"):
        PreannotationConfig(enabled=True, checkpoint=None)


def test_export_split_never_random() -> None:
    with pytest.raises(ValidationError):
        ExportConfig(split_strategy="random")  # type: ignore[arg-type]


def test_export_fractions_must_leave_train() -> None:
    with pytest.raises(ValidationError, match="< 1.0"):
        ExportConfig(val_fraction=0.6, test_fraction=0.5)


def test_extra_keys_forbidden() -> None:
    cfg = _example().model_dump()
    cfg["surprise"] = True
    with pytest.raises(ValidationError):
        ProjectConfig.model_validate(cfg)
