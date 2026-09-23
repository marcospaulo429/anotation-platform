"""Classes: listar e adicionar NO FINAL (append-only)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from annotation_platform.api.config import Settings
from annotation_platform.contracts.project import load_project

from .conftest import HEADERS, project_dir


def test_list_classes(client: TestClient, project: str) -> None:
    resp = client.get(f"/annotate/projects/{project}/classes", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["classes"] == [
        {"index": 0, "name": "MD"},
        {"index": 1, "name": "MV"},
    ]


def test_add_class_appends_at_end(client: TestClient, project: str, settings: Settings) -> None:
    resp = client.post(
        f"/annotate/projects/{project}/classes",
        json={"name": "MC"},
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    names = [c["name"] for c in resp.json()["classes"]]
    assert names == ["MD", "MV", "MC"]
    cfg = load_project(project_dir(settings, project) / "project.yaml")
    assert cfg.classes == ["MD", "MV", "MC"]
    events = [
        json.loads(line)
        for line in (project_dir(settings, project) / "meta" / "status.jsonl")
        .read_text()
        .splitlines()
    ]
    added = [e for e in events if e["event"] == "class_added"]
    assert len(added) == 1
    assert added[0]["img"] == "-"
    assert added[0]["class_name"] == "MC"
    assert added[0]["class_index"] == 2


def test_add_duplicate_class_returns_409(client: TestClient, project: str) -> None:
    resp = client.post(
        f"/annotate/projects/{project}/classes",
        json={"name": "MD"},
        headers=HEADERS,
    )
    assert resp.status_code == 409


def test_classes_unknown_project_404(client: TestClient) -> None:
    assert client.get("/annotate/projects/nope/classes", headers=HEADERS).status_code == 404
