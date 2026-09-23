"""Labels: leitura por fonte, draft (base_version), commit e revert."""

from __future__ import annotations

import hashlib
import json

from fastapi.testclient import TestClient

from annotation_platform.api.config import Settings

from .conftest import HEADERS, make_draft, project_dir, write_pre_labels

EMPTY_BASE = hashlib.sha256(b"").hexdigest()


def test_get_labels_merged_falls_back_to_pre(
    client: TestClient, project: str, settings: Settings
) -> None:
    text = write_pre_labels(settings, project)
    resp = client.get(
        f"/annotate/projects/{project}/labels/P0001.jpg?source=merged", headers=HEADERS
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "pre"
    assert data["n_boxes"] == 2
    assert data["boxes"][0]["conf"] == 0.9
    assert data["base_version"] == hashlib.sha256(text.encode()).hexdigest()


def test_get_labels_merged_empty(client: TestClient, project: str) -> None:
    resp = client.get(
        f"/annotate/projects/{project}/labels/P0001.jpg?source=merged", headers=HEADERS
    )
    assert resp.status_code == 200
    assert resp.json()["source"] == "none"
    assert resp.json()["boxes"] == []


def test_get_labels_missing_source_404(client: TestClient, project: str) -> None:
    resp = client.get(
        f"/annotate/projects/{project}/labels/P0001.jpg?source=manual", headers=HEADERS
    )
    assert resp.status_code == 404


def test_get_labels_unknown_image_404(client: TestClient, project: str) -> None:
    resp = client.get(f"/annotate/projects/{project}/labels/NOPE.jpg", headers=HEADERS)
    assert resp.status_code == 404


def test_put_draft_ok(client: TestClient, project: str, settings: Settings) -> None:
    doc = make_draft(
        "P0001.jpg",
        EMPTY_BASE,
        boxes=[
            {
                "id": "b1",
                "cls": 0,
                "cx": 0.5,
                "cy": 0.5,
                "w": 0.1,
                "h": 0.1,
                "origin": "human",
                "edited": True,
                "edit_ops": ["create"],
            }
        ],
    )
    resp = client.put(
        f"/annotate/projects/{project}/labels/P0001.jpg/draft", json=doc, headers=HEADERS
    )
    assert resp.status_code == 200, resp.text
    root = project_dir(settings, project)
    saved = json.loads((root / "labels" / "drafts" / "P0001.json").read_text())
    assert saved["boxes"][0]["id"] == "b1"
    events = [
        json.loads(line) for line in (root / "meta" / "status.jsonl").read_text().splitlines()
    ]
    assert any(e["event"] == "draft_saved" for e in events)
    # GET source=draft devolve o documento salvo
    resp = client.get(
        f"/annotate/projects/{project}/labels/P0001.jpg?source=draft", headers=HEADERS
    )
    assert resp.status_code == 200
    assert resp.json()["boxes"][0]["cls"] == 0


def test_put_draft_base_version_mismatch_409(client: TestClient, project: str) -> None:
    doc = make_draft("P0001.jpg", "0" * 64)
    resp = client.put(
        f"/annotate/projects/{project}/labels/P0001.jpg/draft", json=doc, headers=HEADERS
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["current_base_version"] == EMPTY_BASE


def test_put_draft_cls_out_of_range_422(client: TestClient, project: str) -> None:
    doc = make_draft(
        "P0001.jpg",
        EMPTY_BASE,
        boxes=[
            {
                "id": "b1",
                "cls": 7,
                "cx": 0.5,
                "cy": 0.5,
                "w": 0.1,
                "h": 0.1,
                "origin": "human",
            }
        ],
    )
    resp = client.put(
        f"/annotate/projects/{project}/labels/P0001.jpg/draft", json=doc, headers=HEADERS
    )
    assert resp.status_code == 422


def test_put_draft_image_mismatch_422(client: TestClient, project: str) -> None:
    doc = make_draft("OTHER.jpg", EMPTY_BASE)
    resp = client.put(
        f"/annotate/projects/{project}/labels/P0001.jpg/draft", json=doc, headers=HEADERS
    )
    assert resp.status_code == 422


def _put_and_commit(client: TestClient, project: str) -> None:
    doc = make_draft(
        "P0001.jpg",
        EMPTY_BASE,
        boxes=[
            {
                "id": "b1",
                "cls": 1,
                "cx": 0.3,
                "cy": 0.3,
                "w": 0.05,
                "h": 0.05,
                "origin": "human",
                "edit_ops": ["create"],
            }
        ],
    )
    resp = client.put(
        f"/annotate/projects/{project}/labels/P0001.jpg/draft", json=doc, headers=HEADERS
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(f"/annotate/projects/{project}/labels/P0001.jpg/commit", headers=HEADERS)
    assert resp.status_code == 200, resp.text


def test_commit_writes_manual_and_events(
    client: TestClient, project: str, settings: Settings
) -> None:
    _put_and_commit(client, project)
    root = project_dir(settings, project)
    manual = (root / "labels" / "manual" / "P0001.txt").read_text()
    assert manual == "1 0.300000 0.300000 0.050000 0.050000\n"
    events = [
        json.loads(line) for line in (root / "meta" / "status.jsonl").read_text().splitlines()
    ]
    kinds = [e["event"] for e in events]
    assert "draft_committed" in kinds
    assert kinds[-1] == "done"
    # merged agora resolve para manual
    resp = client.get(f"/annotate/projects/{project}/labels/P0001.jpg", headers=HEADERS)
    assert resp.json()["source"] == "manual"
    assert resp.json()["boxes"] == [{"cls": 1, "cx": 0.3, "cy": 0.3, "w": 0.05, "h": 0.05}]


def test_commit_without_draft_404(client: TestClient, project: str) -> None:
    resp = client.post(f"/annotate/projects/{project}/labels/P0001.jpg/commit", headers=HEADERS)
    assert resp.status_code == 404


def test_revert_recreates_draft_from_pre(
    client: TestClient, project: str, settings: Settings
) -> None:
    text = write_pre_labels(settings, project)
    resp = client.post(
        f"/annotate/projects/{project}/labels/P0001.jpg/revert?to=pre", headers=HEADERS
    )
    assert resp.status_code == 200, resp.text
    doc = resp.json()
    assert doc["base_version"] == hashlib.sha256(text.encode()).hexdigest()
    assert len(doc["boxes"]) == 2
    assert all(b["origin"] == "model" for b in doc["boxes"])
    assert doc["boxes"][0]["model_conf"] == 0.9
    root = project_dir(settings, project)
    assert (root / "labels" / "drafts" / "P0001.json").is_file()
    events = [
        json.loads(line) for line in (root / "meta" / "status.jsonl").read_text().splitlines()
    ]
    assert any(e["event"] == "reverted" for e in events)


def test_revert_without_pre_404(client: TestClient, project: str) -> None:
    resp = client.post(
        f"/annotate/projects/{project}/labels/P0001.jpg/revert?to=pre", headers=HEADERS
    )
    assert resp.status_code == 404


def test_revert_after_commit_removes_manual_and_allows_save(
    client: TestClient, project: str, settings: Settings
) -> None:
    """C1: commit -> revert -> save não pode travar em 409 nem exportar a label revertida."""
    # 1. commit de uma label manual
    _put_and_commit(client, project)
    root = project_dir(settings, project)
    manual = root / "labels" / "manual" / "P0001.txt"
    assert manual.is_file()
    # 2. existe pré-anotação do modelo
    write_pre_labels(settings, project)
    # 3. revert: manual some e draft volta como origem model
    resp = client.post(
        f"/annotate/projects/{project}/labels/P0001.jpg/revert?to=pre", headers=HEADERS
    )
    assert resp.status_code == 200, resp.text
    assert not manual.exists(), "revert deve remover o manual/ (label revertida não vai pro export)"
    # 4. save do draft revertido NÃO pode dar 409
    doc = resp.json()
    doc["updated_at"] = "2026-09-23T15:00:00"
    resp = client.put(
        f"/annotate/projects/{project}/labels/P0001.jpg/draft", json=doc, headers=HEADERS
    )
    assert resp.status_code == 200, f"save após revert não pode dar 409: {resp.text}"
