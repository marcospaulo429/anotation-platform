"""Auth: X-API-Key obrigatória; app falha no startup sem API_KEY."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from annotation_platform.api.config import Settings
from annotation_platform.api.main import create_app

from .conftest import API_KEY, HEADERS


def test_missing_key_returns_401(client: TestClient) -> None:
    resp = client.get("/annotate/projects")
    assert resp.status_code == 401


def test_wrong_key_returns_403(client: TestClient) -> None:
    resp = client.get("/annotate/projects", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 403


def test_valid_key_returns_200(client: TestClient) -> None:
    resp = client.get("/annotate/projects", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json() == {"projects": []}


def test_health_does_not_require_key(client: TestClient) -> None:
    assert client.get("/health").status_code == 200


def test_startup_fails_without_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="API_KEY"):
        create_app(Settings(api_key=None, annotate_root=tmp_path))


def test_api_key_constant_used() -> None:
    assert API_KEY == "test-key"
