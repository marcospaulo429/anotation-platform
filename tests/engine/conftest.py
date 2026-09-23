"""Shared fixtures for engine tests: a minimal valid project on disk."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

CLASSES = ["MD", "MV"]


def make_project(tmp_path: Path, *, checkpoint_sha256: str | None = None) -> Path:
    """Create a minimal project layout: project.yaml + checkpoint + 2 active images."""
    root = tmp_path / "proj"
    active = root / "images" / "active"
    active.mkdir(parents=True)
    ckpt = tmp_path / "fake.pt"
    ckpt.write_bytes(b"fake-weights")
    for name in ("a.jpg", "b.jpg"):
        (active / name).write_bytes(b"\xff\xd8fake-image")
    preannotation: dict = {
        "enabled": True,
        "checkpoint": str(ckpt),
        "engine": "sahi",
        "imgsz": 1920,
        "conf_threshold": 0.25,
        "iou_threshold": 0.7,
        "slice": {"size": 640, "overlap": 0.2},
    }
    if checkpoint_sha256 is not None:
        preannotation["checkpoint_sha256"] = checkpoint_sha256
    project = {
        "schema_version": 1,
        "name": "Test Project",
        "slug": "test-proj",
        "created_at": "2026-09-23T00:00:00",
        "created_by": "test",
        "classes": CLASSES,
        "image_width": 1920,
        "image_height": 1080,
        "preannotation": preannotation,
    }
    (root / "project.yaml").write_text(yaml.safe_dump(project, sort_keys=False), encoding="utf-8")
    return root


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return make_project(tmp_path)
