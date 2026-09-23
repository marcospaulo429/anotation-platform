"""Import/export: rotas são wrappers sobre dataset_ops (monkeypatched)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from annotation_platform import dataset_ops
from annotation_platform.api.config import Settings
from annotation_platform.dataset_ops import ExportManifest, ImportReport
from annotation_platform.dataset_ops.exporter import SplitCounts

from .conftest import HEADERS, project_dir


def _fake_report(dry_run: bool) -> ImportReport:
    return ImportReport(dry_run=dry_run, images_total=3, images_imported=0 if dry_run else 3)


def _fake_manifest() -> ExportManifest:
    counts = SplitCounts(images=1, boxes=2, plates=["P1"])
    return ExportManifest(
        version=1,
        created_at="2026-09-23T15:00:00",
        created_by="tester",
        plate_key_rule="stem[:_]",
        classes=["MD", "MV"],
        train=counts,
        val=counts,
        test=counts,
    )


def test_import_dry_run_default(
    client: TestClient, project: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {}

    def fake_import(project_root, images_dir, labels_dir, *, user, copy, dry_run):
        calls.update(user=user, copy=copy, dry_run=dry_run)
        return _fake_report(dry_run)

    monkeypatch.setattr(dataset_ops, "import_dataset", fake_import)
    resp = client.post(
        f"/annotate/projects/{project}/import",
        json={"images_dir": "/src/images", "labels_dir": "/src/labels"},
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["dry_run"] is True
    assert calls["dry_run"] is True


def test_import_real_run(client: TestClient, project: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_import(project_root, images_dir, labels_dir, *, user, copy, dry_run):
        return _fake_report(dry_run)

    monkeypatch.setattr(dataset_ops, "import_dataset", fake_import)
    resp = client.post(
        f"/annotate/projects/{project}/import",
        json={"images_dir": "/src/images", "labels_dir": "/src/labels", "dry_run": False},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["dry_run"] is False
    assert resp.json()["images_imported"] == 3


def test_import_not_implemented_returns_501(
    client: TestClient, project: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_import(*args, **kwargs):
        raise NotImplementedError("anno-data: implement import_dataset")

    monkeypatch.setattr(dataset_ops, "import_dataset", fake_import)
    resp = client.post(
        f"/annotate/projects/{project}/import",
        json={"images_dir": "/x", "labels_dir": "/y"},
        headers=HEADERS,
    )
    assert resp.status_code == 501


def test_export_returns_manifest(
    client: TestClient, project: str, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dataset_ops, "export_dataset", lambda root, *, user: _fake_manifest())
    resp = client.post(
        f"/annotate/projects/{project}/export", json={"user": "tester"}, headers=HEADERS
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["version"] == 1
    # O evento `exported` é responsabilidade do dataset_ops.export_dataset
    # (aqui mockado) — a rota NÃO deve duplicá-lo (bug I4 corrigido).
    log = project_dir(settings, project) / "meta" / "status.jsonl"
    if log.exists():
        events = [json.loads(line) for line in log.read_text().splitlines()]
        assert not any(e["event"] == "exported" for e in events), "rota duplicou o evento"


def test_export_not_implemented_returns_501(
    client: TestClient, project: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_export(*args, **kwargs):
        raise NotImplementedError("anno-data: implement export_dataset")

    monkeypatch.setattr(dataset_ops, "export_dataset", fake_export)
    resp = client.post(f"/annotate/projects/{project}/export", json={}, headers=HEADERS)
    assert resp.status_code == 501


def test_list_exports(client: TestClient, project: str, settings: Settings) -> None:
    root = project_dir(settings, project)
    v1 = root / "exports" / "v1"
    v1.mkdir(parents=True)
    (v1 / "manifest.json").write_text(_fake_manifest().model_dump_json(), encoding="utf-8")
    resp = client.get(f"/annotate/projects/{project}/exports", headers=HEADERS)
    assert resp.status_code == 200
    items = resp.json()["exports"]
    assert len(items) == 1
    assert items[0]["version"] == "v1"
    assert items[0]["manifest"]["version"] == 1
