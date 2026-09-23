"""Jobs: preannotate registra job pending (sem submeter Slurm) e listagem."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from annotation_platform.api.config import Settings

from .conftest import HEADERS, project_dir


def test_preannotate_creates_pending_job(
    client: TestClient, project: str, settings: Settings
) -> None:
    resp = client.post(f"/annotate/projects/{project}/preannotate", json={}, headers=HEADERS)
    assert resp.status_code == 202, resp.text
    job = resp.json()
    assert job["status"] == "pending"
    assert job["images"] == ["P0001.jpg"]
    jobs_dir = project_dir(settings, project) / "meta" / "jobs"
    saved = json.loads((jobs_dir / f"{job['job_id']}.json").read_text())
    assert saved["status"] == "pending"
    assert "params" in saved


def test_preannotate_explicit_images(client: TestClient, project: str) -> None:
    resp = client.post(
        f"/annotate/projects/{project}/preannotate",
        json={"images": ["P0001.jpg"]},
        headers=HEADERS,
    )
    assert resp.status_code == 202
    assert resp.json()["images"] == ["P0001.jpg"]


def test_preannotate_missing_image_404(client: TestClient, project: str) -> None:
    resp = client.post(
        f"/annotate/projects/{project}/preannotate",
        json={"images": ["NOPE.jpg"]},
        headers=HEADERS,
    )
    assert resp.status_code == 404


def test_list_jobs(client: TestClient, project: str) -> None:
    client.post(f"/annotate/projects/{project}/preannotate", json={}, headers=HEADERS)
    resp = client.get(f"/annotate/projects/{project}/jobs", headers=HEADERS)
    assert resp.status_code == 200
    jobs = resp.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["status"] == "pending"
