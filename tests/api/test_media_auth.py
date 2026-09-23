"""Testes da integração API↔SPA: auth por query param em mídia e mount estático."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from annotation_platform.api.config import Settings
from annotation_platform.api.main import create_app

from .conftest import API_KEY, HEADERS


def test_thumb_accepts_api_key_query_param(client: TestClient, project: str) -> None:
    resp = client.get(f"/annotate/projects/{project}/images/P0001.jpg/thumb?api_key={API_KEY}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"


def test_thumb_rejects_wrong_query_key(client: TestClient, project: str) -> None:
    resp = client.get(f"/annotate/projects/{project}/images/P0001.jpg/thumb?api_key=wrong")
    assert resp.status_code == 403


def test_thumb_still_accepts_header(client: TestClient, project: str) -> None:
    resp = client.get(f"/annotate/projects/{project}/images/P0001.jpg/thumb", headers=HEADERS)
    assert resp.status_code == 200


def test_media_routes_require_auth(client: TestClient, project: str) -> None:
    for suffix in ("thumb", "full", "tiles/0/0"):
        resp = client.get(f"/annotate/projects/{project}/images/P0001.jpg/{suffix}")
        assert resp.status_code == 401, suffix


def test_non_media_routes_reject_query_key(client: TestClient, project: str) -> None:
    """Query param NÃO vale fora dos endpoints de mídia."""
    resp = client.get(f"/annotate/projects/{project}/images?api_key={API_KEY}")
    assert resp.status_code == 401


def test_spa_mounted_when_web_dir_exists(settings: Settings, tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<h1>spa</h1>", encoding="utf-8")
    settings.web_dir = web
    client = TestClient(create_app(settings))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "<h1>spa</h1>" in resp.text


def test_spa_absent_is_fine(settings: Settings) -> None:
    settings.web_dir = settings.annotate_root / "nao-existe"
    client = TestClient(create_app(settings))
    assert client.get("/health").status_code == 200
    assert client.get("/").status_code == 404


def test_api_routes_win_over_spa_mount(settings: Settings, tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("spa", encoding="utf-8")
    settings.web_dir = web
    client = TestClient(create_app(settings))
    resp = client.get("/annotate/projects", headers=HEADERS)
    assert resp.status_code == 200


def test_create_app_requires_api_key(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="API_KEY"):
        create_app(Settings(api_key=None, annotate_root=tmp_path))
