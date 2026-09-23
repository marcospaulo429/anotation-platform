"""Projetos: criar (manual e com checkpoint mockado), listar, ler, PATCH."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from annotation_platform.api.config import Settings
from annotation_platform.contracts.project import load_project

from .conftest import HEADERS, project_dir


def test_create_project_manual(client: TestClient, settings: Settings) -> None:
    resp = client.post(
        "/annotate/projects",
        json={"name": "Placas Q4", "classes": ["MD", "MV"]},
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["slug"] == "placas-q4"
    assert data["classes"] == ["MD", "MV"]
    assert data["preannotation"]["enabled"] is False
    root = project_dir(settings, "placas-q4")
    assert (root / "project.yaml").is_file()
    for sub in ("images/incoming", "images/active", "labels/drafts", "labels/manual", "meta/jobs"):
        assert (root / sub).is_dir()
    cfg = load_project(root / "project.yaml")
    assert cfg.classes == ["MD", "MV"]


def test_create_project_requires_classes_without_checkpoint(client: TestClient) -> None:
    resp = client.post("/annotate/projects", json={"name": "Sem Classes"}, headers=HEADERS)
    assert resp.status_code == 422


def test_create_project_with_checkpoint(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "annotation_platform.api.projects._load_model_names",
        lambda ckpt: ["MD", "MV", "MC"],
    )
    resp = client.post(
        "/annotate/projects",
        json={
            "name": "Pre Anotado",
            "preannotation": {"enabled": True, "checkpoint": "/fake/best.pt"},
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["classes"] == ["MD", "MV", "MC"]
    assert data["preannotation"]["enabled"] is True
    assert data["preannotation"]["checkpoint"] == "/fake/best.pt"


def test_create_project_checkpoint_unreadable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(ckpt: str) -> list[str]:
        raise FileNotFoundError(ckpt)

    monkeypatch.setattr("annotation_platform.api.projects._load_model_names", _boom)
    resp = client.post(
        "/annotate/projects",
        json={
            "name": "Ckpt Ruim",
            "preannotation": {"enabled": True, "checkpoint": "/nope.pt"},
        },
        headers=HEADERS,
    )
    assert resp.status_code == 422


def test_create_duplicate_slug_returns_409(client: TestClient, project: str) -> None:
    resp = client.post(
        "/annotate/projects",
        json={"name": "Demo", "classes": ["MD"]},
        headers=HEADERS,
    )
    assert resp.status_code == 409


def test_list_projects_with_stats(client: TestClient, project: str) -> None:
    resp = client.get("/annotate/projects", headers=HEADERS)
    assert resp.status_code == 200
    items = resp.json()["projects"]
    assert len(items) == 1
    assert items[0]["slug"] == project
    assert items[0]["n_classes"] == 2
    assert items[0]["n_images"] == 1


def test_get_project(client: TestClient, project: str) -> None:
    resp = client.get(f"/annotate/projects/{project}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["config"]["classes"] == ["MD", "MV"]


def test_get_unknown_project_returns_404(client: TestClient) -> None:
    assert client.get("/annotate/projects/nope", headers=HEADERS).status_code == 404


def test_patch_append_classes_ok(client: TestClient, project: str, settings: Settings) -> None:
    resp = client.patch(
        f"/annotate/projects/{project}",
        json={"classes": ["MD", "MV", "MC"]},
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["classes"] == ["MD", "MV", "MC"]
    cfg = load_project(project_dir(settings, project) / "project.yaml")
    assert cfg.classes == ["MD", "MV", "MC"]


def test_patch_reorder_classes_returns_409(client: TestClient, project: str) -> None:
    resp = client.patch(
        f"/annotate/projects/{project}",
        json={"classes": ["MV", "MD"]},
        headers=HEADERS,
    )
    assert resp.status_code == 409


def test_patch_checkpoint_prefix_compatible(
    client: TestClient, project: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "annotation_platform.api.projects._load_model_names", lambda ckpt: ["MD", "MV"]
    )
    resp = client.patch(
        f"/annotate/projects/{project}",
        json={"checkpoint": "/fake/v2.pt"},
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["preannotation"]["checkpoint"] == "/fake/v2.pt"


def test_patch_checkpoint_incompatible_returns_409(
    client: TestClient, project: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "annotation_platform.api.projects._load_model_names", lambda ckpt: ["OUTRA", "MV"]
    )
    resp = client.patch(
        f"/annotate/projects/{project}",
        json={"checkpoint": "/fake/v3.pt"},
        headers=HEADERS,
    )
    assert resp.status_code == 409
