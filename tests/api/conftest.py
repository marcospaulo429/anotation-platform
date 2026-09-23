"""Fixtures dos testes da API: settings em tmp_path, client e projeto fake."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from annotation_platform.api.config import Settings
from annotation_platform.api.main import create_app
from annotation_platform.contracts.common import atomic_write_text
from annotation_platform.contracts.project import PreannotationConfig, ProjectConfig, dump_project

API_KEY = "test-key"
HEADERS = {"X-API-Key": API_KEY}

PROJECT_SUBDIRS = (
    "images/incoming",
    "images/active",
    "labels/pre",
    "labels/pre_meta",
    "labels/drafts",
    "labels/manual",
    "labels/merged",
    "meta/jobs",
    "exports",
)


def make_image_bytes(width: int = 1920, height: int = 1080, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (128, 64, 32)).save(buf, fmt)
    return buf.getvalue()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(api_key=API_KEY, annotate_root=tmp_path)


@pytest.fixture()
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


@pytest.fixture()
def project(settings: Settings) -> str:
    """Projeto fake 'demo' (classes MD/MV) com uma imagem 1920x1080 ativa."""
    slug = "demo"
    root = settings.annotate_root / "projects" / slug
    for sub in PROJECT_SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    cfg = ProjectConfig(
        name="Demo",
        slug=slug,
        created_at="2026-09-23T00:00:00",
        created_by="test",
        classes=["MD", "MV"],
        preannotation=PreannotationConfig(enabled=False),
    )
    atomic_write_text(root / "project.yaml", dump_project(cfg))
    (root / "images" / "active" / "P0001.jpg").write_bytes(make_image_bytes(fmt="JPEG"))
    return slug


def project_dir(settings: Settings, slug: str) -> Path:
    return settings.annotate_root / "projects" / slug


def write_pre_labels(settings: Settings, slug: str, stem: str = "P0001") -> str:
    """Grava labels/pre/<stem>.txt + pre_meta e devolve o texto YOLO."""
    root = project_dir(settings, slug)
    text = "0 0.500000 0.500000 0.100000 0.100000\n1 0.250000 0.250000 0.050000 0.050000\n"
    atomic_write_text(root / "labels" / "pre" / f"{stem}.txt", text)
    meta = {
        "schema_version": 1,
        "image": f"{stem}.jpg",
        "created_at": "2026-09-23T10:00:00",
        "model": {"checkpoint": "/fake/ckpt.pt", "sha256": "ab" * 32, "wandb_run": None},
        "engine": "sahi",
        "params": {"imgsz": 1920, "conf": 0.25, "iou": 0.7, "slice": 640, "overlap": 0.2},
        "inference_seconds": 1.0,
        "boxes": [
            {"cls": 0, "cx": 0.5, "cy": 0.5, "w": 0.1, "h": 0.1, "conf": 0.9},
            {"cls": 1, "cx": 0.25, "cy": 0.25, "w": 0.05, "h": 0.05, "conf": 0.7},
        ],
    }
    (root / "labels" / "pre_meta" / f"{stem}.json").write_text(json.dumps(meta), encoding="utf-8")
    return text


def make_draft(img: str, base_version: str, boxes: list[dict] | None = None, **kw) -> dict:
    return {
        "schema_version": 1,
        "image": img,
        "base_version": base_version,
        "updated_at": "2026-09-23T14:00:00",
        "updated_by": "tester",
        "ops_since_commit": 1,
        "tiles_seen": [],
        "boxes": boxes or [],
        "history": [],
        **kw,
    }
