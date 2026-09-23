"""Tests for dataset_ops.export_dataset (synthetic data in tmp_path only)."""

from __future__ import annotations

import os

import pytest
import yaml

from annotation_platform.contracts.common import read_jsonl
from annotation_platform.dataset_ops import export_dataset
from annotation_platform.dataset_ops.exporter import DEFAULT_PLATE_KEY_RULE

LINE = "0 0.500000 0.500000 0.100000 0.200000"
N_PLATES = 10
IMAGES_PER_PLATE = 2


def _populate(project, write_image, write_label, n_plates=N_PLATES) -> None:
    for i in range(1, n_plates + 1):
        for j in range(IMAGES_PER_PLATE):
            stem = f"P{i:03d}_{j}"
            write_image(project / "images" / "active" / f"{stem}.jpg")
            write_label(project / "labels" / "manual" / f"{stem}.txt", [LINE])


def test_split_is_by_plate_without_leakage(make_project, write_image, write_label):
    project = make_project()  # val=0.2, test=0.2
    _populate(project, write_image, write_label)

    manifest = export_dataset(project, user="marcos")

    train, val, test = (
        set(manifest.train.plates),
        set(manifest.val.plates),
        set(manifest.test.plates),
    )
    assert train.isdisjoint(val)
    assert train.isdisjoint(test)
    assert val.isdisjoint(test)
    assert train | val | test == {f"P{i:03d}" for i in range(1, N_PLATES + 1)}
    assert (len(train), len(val), len(test)) == (6, 2, 2)
    assert manifest.train.images == 12
    assert manifest.train.boxes == 12
    assert manifest.val.images == 4
    assert manifest.test.images == 4
    assert manifest.split_strategy == "by_plate"
    assert manifest.plate_key_rule == DEFAULT_PLATE_KEY_RULE
    # whole plates exported: every split dir holds exactly its plates' images
    for split, plates in (("train", train), ("val", val), ("test", test)):
        imgs = sorted(p.name for p in (project / "exports" / "v1" / "images" / split).iterdir())
        assert imgs == sorted(f"{plate}_{j}.jpg" for plate in plates for j in range(2))
        lbls = sorted(p.name for p in (project / "exports" / "v1" / "labels" / split).iterdir())
        assert lbls == sorted(f"{plate}_{j}.txt" for plate in plates for j in range(2))


def test_export_is_reproducible(make_project, write_image, write_label):
    project = make_project()
    _populate(project, write_image, write_label)

    m1 = export_dataset(project, user="marcos")
    m2 = export_dataset(project, user="marcos")

    assert (m1.train.plates, m1.val.plates, m1.test.plates) == (
        m2.train.plates,
        m2.val.plates,
        m2.test.plates,
    )


def test_versions_increment(make_project, write_image, write_label):
    project = make_project()
    _populate(project, write_image, write_label)

    m1 = export_dataset(project, user="marcos")
    m2 = export_dataset(project, user="marcos")

    assert (m1.version, m2.version) == (1, 2)
    assert (project / "exports" / "v1" / "manifest.json").exists()
    assert (project / "exports" / "v2" / "manifest.json").exists()


def test_data_yaml_matches_project_classes(make_project, write_image, write_label):
    project = make_project(classes=["MD", "MV", "MC"])
    _populate(project, write_image, write_label)
    export_dataset(project, user="marcos")

    data = yaml.safe_load((project / "exports" / "v1" / "data.yaml").read_text(encoding="utf-8"))

    assert data["names"] == ["MD", "MV", "MC"]
    assert data["nc"] == 3
    assert data["path"] == "exports/v1"
    assert data["train"] == "images/train"
    assert data["val"] == "images/val"
    assert data["test"] == "images/test"


def test_drafts_never_enter_export(make_project, write_image, write_label):
    project = make_project()
    _populate(project, write_image, write_label)
    # image with ONLY a draft (no manual label) + image with nothing at all
    write_image(project / "images" / "active" / "P999_0.jpg")
    (project / "labels" / "drafts" / "P999_0.json").write_text("{}", encoding="utf-8")
    write_image(project / "images" / "active" / "P998_0.jpg")

    manifest = export_dataset(project, user="marcos")

    total = manifest.train.images + manifest.val.images + manifest.test.images
    assert total == N_PLATES * IMAGES_PER_PLATE
    plates = set(manifest.train.plates) | set(manifest.val.plates) | set(manifest.test.plates)
    assert "P999" not in plates and "P998" not in plates
    assert list((project / "exports" / "v1").rglob("P999_0.*")) == []
    assert list((project / "exports" / "v1").rglob("P998_0.*")) == []


def test_invalid_manual_label_aborts_without_partial_export(make_project, write_image, write_label):
    project = make_project()
    _populate(project, write_image, write_label)
    write_label(project / "labels" / "manual" / "P005_0.txt", ["9 0.5 0.5 0.1 0.2"])

    with pytest.raises(ValueError, match="out of range"):
        export_dataset(project, user="marcos")

    assert not (project / "exports" / "v1").exists()
    assert not (project / "meta" / "status.jsonl").exists()


def test_export_appends_single_exported_event(make_project, write_image, write_label):
    project = make_project()
    _populate(project, write_image, write_label)

    export_dataset(project, user="marcos")

    events = read_jsonl(project / "meta" / "status.jsonl")
    assert len(events) == 1
    (event,) = events
    assert event["event"] == "exported"
    assert event["img"] == "-"
    assert event["user"] == "marcos"
    assert event["version"] == 1
    assert event["counts"]["train"] == {"images": 12, "boxes": 12}


def test_exported_files_are_hardlinks(make_project, write_image, write_label):
    project = make_project()
    _populate(project, write_image, write_label)
    export_dataset(project, user="marcos")

    src_label = project / "labels" / "manual" / "P001_0.txt"
    dst_label = next((project / "exports" / "v1" / "labels").rglob("P001_0.txt"))
    assert os.stat(src_label).st_ino == os.stat(dst_label).st_ino
    src_image = project / "images" / "active" / "P001_0.jpg"
    dst_image = next((project / "exports" / "v1" / "images").rglob("P001_0.jpg"))
    assert os.stat(src_image).st_ino == os.stat(dst_image).st_ino


def test_nothing_to_export_raises(make_project):
    project = make_project()

    with pytest.raises(ValueError, match="nothing to export"):
        export_dataset(project, user="marcos")


def test_custom_plate_key(make_project, write_image, write_label):
    project = make_project()
    _populate(project, write_image, write_label, n_plates=3)

    key = lambda name: name.split("_")[1].split(".")[0]  # noqa: E731
    manifest = export_dataset(project, user="marcos", plate_key=key)

    plates = set(manifest.train.plates) | set(manifest.val.plates) | set(manifest.test.plates)
    assert plates == {"0", "1"}
    assert "custom callable" in manifest.plate_key_rule


def test_split_fractions_too_large_raise(make_project, write_image, write_label):
    project = make_project(val_fraction=0.5, test_fraction=0.49)
    _populate(project, write_image, write_label, n_plates=2)

    with pytest.raises(ValueError, match="train would be empty"):
        export_dataset(project, user="marcos")
