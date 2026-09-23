"""Stats: contagens por status, correction rate e cobertura de tiles."""

from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

from .conftest import HEADERS, make_draft

EMPTY_BASE = hashlib.sha256(b"").hexdigest()


def _commit_one_model_box(client: TestClient, project: str) -> None:
    doc = make_draft(
        "P0001.jpg",
        EMPTY_BASE,
        tiles_seen=[0, 1, 2, 3],
        boxes=[
            {
                "id": "b1",
                "cls": 0,
                "cx": 0.5,
                "cy": 0.5,
                "w": 0.1,
                "h": 0.1,
                "origin": "model",
                "model_conf": 0.8,
                "edited": True,
                "edit_ops": ["move", "resize"],
            }
        ],
    )
    resp = client.put(
        f"/annotate/projects/{project}/labels/P0001.jpg/draft", json=doc, headers=HEADERS
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(f"/annotate/projects/{project}/labels/P0001.jpg/commit", headers=HEADERS)
    assert resp.status_code == 200, resp.text


def test_stats_empty_project(client: TestClient, project: str) -> None:
    resp = client.get(f"/annotate/projects/{project}/stats", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["images"] == 1
    assert data["status_counts"] == {"unlabeled": 1}
    assert data["correction_rate"] is None
    assert data["tiles_seen_avg"] is None


def test_stats_after_commit(client: TestClient, project: str) -> None:
    _commit_one_model_box(client, project)
    resp = client.get(f"/annotate/projects/{project}/stats", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status_counts"] == {"done": 1}
    assert data["correction_rate"] == 2.0  # 2 edit_ops / 1 caixa origin=model
    assert data["model_boxes_reviewed"] == 1
    assert data["tiles_seen_avg"] == 4.0
    assert data["drafts"] == 1
