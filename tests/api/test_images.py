"""Imagens: upload válido/inválido, listagem paginada, thumb, tiles, full."""

from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient
from PIL import Image

from annotation_platform.api.config import Settings

from .conftest import HEADERS, make_image_bytes, project_dir


def _upload(client: TestClient, slug: str, name: str, content: bytes) -> object:
    return client.post(
        f"/annotate/projects/{slug}/images",
        files=[("files", (name, content, "application/octet-stream"))],
        headers=HEADERS,
    )


def test_upload_valid_image(client: TestClient, project: str, settings: Settings) -> None:
    resp = _upload(client, project, "P0002.jpg", make_image_bytes(fmt="JPEG"))
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["uploaded"][0]["image"] == "P0002.jpg"
    assert data["errors"] == []
    root = project_dir(settings, project)
    assert (root / "images" / "active" / "P0002.jpg").is_file()
    assert not (root / "images" / "incoming" / "P0002.jpg").exists()
    events = [
        json.loads(line) for line in (root / "meta" / "status.jsonl").read_text().splitlines()
    ]
    assert any(e["event"] == "uploaded" and e["img"] == "P0002.jpg" for e in events)


def test_upload_multi_partial_errors_do_not_abort(
    client: TestClient, project: str, settings: Settings
) -> None:
    """Lote misto: válidas entram, inválidas viram relatório (sem abortar)."""
    resp = client.post(
        f"/annotate/projects/{project}/images",
        files=[
            ("files", ("ok1.jpg", make_image_bytes(fmt="JPEG"), "image/jpeg")),
            ("files", ("bad.gif", make_image_bytes(fmt="JPEG"), "image/gif")),
            ("files", ("ok2.jpg", make_image_bytes(fmt="JPEG"), "image/jpeg")),
        ],
        headers=HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert [u["image"] for u in data["uploaded"]] == ["ok1.jpg", "ok2.jpg"]
    assert len(data["errors"]) == 1
    assert data["errors"][0]["file"] == "bad.gif"
    root = project_dir(settings, project)
    assert (root / "images" / "active" / "ok1.jpg").is_file()
    assert (root / "images" / "active" / "ok2.jpg").is_file()
    assert not (root / "images" / "active" / "bad.gif").exists()


def test_upload_wrong_dimensions_reported_in_errors(client: TestClient, project: str) -> None:
    resp = _upload(client, project, "small.jpg", make_image_bytes(640, 480, "JPEG"))
    assert resp.status_code == 201
    data = resp.json()
    assert data["uploaded"] == []
    assert "dimensões" in data["errors"][0]["detail"]


def test_upload_bad_extension_reported(client: TestClient, project: str) -> None:
    resp = _upload(client, project, "x.gif", make_image_bytes(fmt="JPEG"))
    assert resp.status_code == 201
    assert resp.json()["errors"][0]["file"] == "x.gif"


def test_upload_not_an_image_reported(client: TestClient, project: str, settings: Settings) -> None:
    resp = _upload(client, project, "fake.jpg", b"not an image at all")
    assert resp.status_code == 201
    assert resp.json()["errors"]
    root = project_dir(settings, project)
    assert not (root / "images" / "incoming" / "fake.jpg").exists()


def test_upload_to_unknown_project_404(client: TestClient) -> None:
    resp = _upload(client, "nope", "a.jpg", make_image_bytes(fmt="JPEG"))
    assert resp.status_code == 404


def test_reupload_same_name_rejected_409(client: TestClient, project: str) -> None:
    """C2: reenviar o mesmo nome não pode sobrescrever a imagem ativa
    (deixaria labels da foto anterior órfãs associadas a outra imagem)."""
    first = _upload(client, project, "P0009.jpg", make_image_bytes(fmt="JPEG"))
    assert first.status_code == 201
    second = _upload(client, project, "P0009.jpg", make_image_bytes(fmt="JPEG"))
    assert second.status_code == 201  # lote 201, mas o erro vai no relatório
    data = second.json()
    assert data["uploaded"] == []
    assert data["errors"][0]["file"] == "P0009.jpg"
    assert "409" in str(data["errors"][0]["detail"]) or "já existe" in data["errors"][0]["detail"]


def test_list_images_pagination(client: TestClient, project: str) -> None:
    _upload(client, project, "P0002.jpg", make_image_bytes(fmt="JPEG"))
    _upload(client, project, "P0003.jpg", make_image_bytes(fmt="JPEG"))
    resp = client.get(f"/annotate/projects/{project}/images?page_size=2", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert [i["img"] for i in data["items"]] == ["P0001.jpg", "P0002.jpg"]
    assert data["next_cursor"] == 2
    resp2 = client.get(f"/annotate/projects/{project}/images?page_size=2&cursor=2", headers=HEADERS)
    assert [i["img"] for i in resp2.json()["items"]] == ["P0003.jpg"]
    assert resp2.json()["next_cursor"] is None


def test_list_images_filter_by_status(client: TestClient, project: str) -> None:
    _upload(client, project, "P0002.jpg", make_image_bytes(fmt="JPEG"))
    # filtro pelo evento cru
    resp = client.get(f"/annotate/projects/{project}/images?status=uploaded", headers=HEADERS)
    assert [i["img"] for i in resp.json()["items"]] == ["P0002.jpg"]
    # filtro pelo status de exibição (uploaded -> unlabeled na UI)
    resp = client.get(f"/annotate/projects/{project}/images?status=unlabeled", headers=HEADERS)
    assert [i["img"] for i in resp.json()["items"]] == ["P0001.jpg", "P0002.jpg"]
    # item expõe os dois
    item = resp.json()["items"][1]
    assert item["status"] == "uploaded"
    assert item["display_status"] == "unlabeled"


def test_thumb_cached(client: TestClient, project: str, settings: Settings) -> None:
    resp = client.get(f"/annotate/projects/{project}/images/P0001.jpg/thumb", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    cached = settings.annotate_root / ".cache" / "thumbs" / project / "P0001.jpg"
    assert cached.is_file()
    with Image.open(cached) as im:
        assert max(im.size) <= 320


def test_tile_native_resolution(client: TestClient, project: str, settings: Settings) -> None:
    resp = client.get(
        f"/annotate/projects/{project}/images/P0001.jpg/tiles/1/0?w=640", headers=HEADERS
    )
    assert resp.status_code == 200
    tile = Image.open(io.BytesIO(resp.content))
    assert tile.size == (640, 640)
    cached = settings.annotate_root / ".cache" / "tiles" / project / "P0001" / "640" / "1_0.jpg"
    assert cached.is_file()


def test_tile_out_of_bounds_404(client: TestClient, project: str) -> None:
    resp = client.get(
        f"/annotate/projects/{project}/images/P0001.jpg/tiles/99/0?w=640", headers=HEADERS
    )
    assert resp.status_code == 404


def test_full_image(client: TestClient, project: str) -> None:
    resp = client.get(f"/annotate/projects/{project}/images/P0001.jpg/full", headers=HEADERS)
    assert resp.status_code == 200
    with Image.open(io.BytesIO(resp.content)) as im:
        assert im.size == (1920, 1080)


def test_missing_image_404(client: TestClient, project: str) -> None:
    resp = client.get(f"/annotate/projects/{project}/images/NOPE.jpg/full", headers=HEADERS)
    assert resp.status_code == 404
