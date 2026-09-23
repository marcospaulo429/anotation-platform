"""Fixtures for dataset_ops tests: synthetic projects/images in tmp_path only.

Real datasets under /home/marcos/Documentos/fly-det/datasets/ are NEVER used.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from annotation_platform.contracts.common import atomic_write_text
from annotation_platform.contracts.project import ProjectConfig, dump_project

# Minimal 1x1 PNG (importer/exporter never decode image bytes).
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a"
    "0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c620001000000ffff03000006000557bfabd4"
    "0000000049454e44ae426082"
)


@pytest.fixture
def make_project(tmp_path: Path) -> Callable[..., Path]:
    """Factory: create a minimal valid project skeleton under tmp_path."""

    def _make(
        *,
        classes: list[str] | tuple[str, ...] = ("MD", "MV"),
        val_fraction: float = 0.2,
        test_fraction: float = 0.2,
    ) -> Path:
        root = tmp_path / "proj"
        cfg = ProjectConfig(
            name="Test Project",
            slug="test-project",
            created_at="2026-09-23T00:00:00+00:00",
            created_by="tester",
            classes=list(classes),
            preannotation={"enabled": False},
            export={"val_fraction": val_fraction, "test_fraction": test_fraction},
        )
        atomic_write_text(root / "project.yaml", dump_project(cfg))
        for sub in (
            "images/incoming",
            "images/active",
            "labels/pre",
            "labels/pre_meta",
            "labels/drafts",
            "labels/manual",
            "labels/merged",
            "meta",
        ):
            (root / sub).mkdir(parents=True, exist_ok=True)
        return root

    return _make


@pytest.fixture
def write_image() -> Callable[[Path], Path]:
    def _write(path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(TINY_PNG)
        return path

    return _write


@pytest.fixture
def write_label() -> Callable[[Path, list[str]], Path]:
    def _write(path: Path, lines: list[str]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return path

    return _write
