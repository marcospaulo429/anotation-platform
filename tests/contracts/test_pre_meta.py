"""Contract tests for pre_meta JSON (PREANNOTATION_PLATFORM.md section 4.3)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from annotation_platform.contracts.pre_meta import ModelRef, PreMeta

# Literal example from PREANNOTATION_PLATFORM.md section 4.3
PRE_META_EXAMPLE: dict = {
    "schema_version": 1,
    "image": "P0012.jpg",
    "created_at": "2026-09-23T10:00:11",
    "model": {
        "checkpoint": "/raid/user_marcospaulo/models/e0_yolo26m_baseline_best.pt",
        "sha256": "a" * 64,
        "wandb_run": "pestline/fly-det/036ef018",
    },
    "engine": "sahi",
    "params": {"imgsz": 1920, "conf": 0.25, "iou": 0.7, "slice": 640, "overlap": 0.2},
    "inference_seconds": 3.41,
    "boxes": [{"cls": 0, "cx": 0.5123, "cy": 0.3312, "w": 0.0210, "h": 0.0365, "conf": 0.83}],
}


def test_md_example_is_valid() -> None:
    meta = PreMeta.model_validate(PRE_META_EXAMPLE)
    assert meta.engine == "sahi"
    assert meta.boxes[0].conf == 0.83
    assert meta.model.sha256 == "a" * 64


def test_sha256_must_be_64_hex_length() -> None:
    with pytest.raises(ValidationError):
        ModelRef(checkpoint="/x.pt", sha256="short")


def test_engine_is_sahi_or_plain() -> None:
    data = {**PRE_META_EXAMPLE, "engine": "magic"}
    with pytest.raises(ValidationError):
        PreMeta.model_validate(data)


def test_box_confidence_bounded() -> None:
    data = {**PRE_META_EXAMPLE, "boxes": [{**PRE_META_EXAMPLE["boxes"][0], "conf": 1.4}]}
    with pytest.raises(ValidationError):
        PreMeta.model_validate(data)


def test_plain_engine_allows_no_slice() -> None:
    data = {
        **PRE_META_EXAMPLE,
        "engine": "plain",
        "params": {"imgsz": 1920, "conf": 0.25, "iou": 0.7},
    }
    meta = PreMeta.model_validate(data)
    assert meta.params.slice is None


def test_json_roundtrip() -> None:
    meta = PreMeta.model_validate(PRE_META_EXAMPLE)
    assert PreMeta.model_validate(meta.model_dump(mode="json")) == meta
