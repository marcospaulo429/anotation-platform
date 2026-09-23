"""Tests for dataset_ops.import_dataset (synthetic data in tmp_path only)."""

from __future__ import annotations

import os

from annotation_platform.contracts.common import read_jsonl
from annotation_platform.dataset_ops import import_dataset


def test_dry_run_validates_without_writing(make_project, write_image, write_label, tmp_path):
    project = make_project()
    images, labels = tmp_path / "in_images", tmp_path / "in_labels"
    write_image(images / "P001_a.jpg")
    write_image(images / "P001_b.jpg")
    write_label(labels / "P001_a.txt", ["0 0.5 0.5 0.1 0.2", "1 0.1 0.2 0.3 0.4"])

    report = import_dataset(project, images, labels, user="marcos", dry_run=True)

    assert report.dry_run is True
    assert report.images_total == 2
    assert report.images_imported == 1
    assert report.images_without_label == 1
    assert report.boxes_total == 2
    assert report.errors == []
    assert list((project / "images" / "active").iterdir()) == []
    assert list((project / "labels" / "manual").iterdir()) == []
    assert not (project / "meta" / "status.jsonl").exists()


def test_import_writes_labels_and_imported_events(make_project, write_image, write_label, tmp_path):
    project = make_project()
    images, labels = tmp_path / "in_images", tmp_path / "in_labels"
    write_image(images / "P001_a.jpg")
    write_label(labels / "P001_a.txt", ["0 0.5 0.5 0.1 0.2", "1 0.1 0.2 0.3 0.4"])

    report = import_dataset(project, images, labels, user="marcos", dry_run=False)

    assert report.images_imported == 1
    assert (project / "images" / "active" / "P001_a.jpg").exists()
    label_out = (project / "labels" / "manual" / "P001_a.txt").read_text(encoding="utf-8")
    assert label_out == (
        "0 0.500000 0.500000 0.100000 0.200000\n1 0.100000 0.200000 0.300000 0.400000\n"
    )
    events = read_jsonl(project / "meta" / "status.jsonl")
    assert [(e["img"], e["event"], e.get("n_boxes")) for e in events] == [
        ("P001_a.jpg", "imported", 2)
    ]
    assert events[0]["user"] == "marcos"


def test_image_without_label_gets_uploaded_event(make_project, write_image, tmp_path):
    project = make_project()
    images, labels = tmp_path / "in_images", tmp_path / "in_labels"
    labels.mkdir()
    write_image(images / "P001_a.jpg")

    report = import_dataset(project, images, labels, user="marcos", dry_run=False)

    assert report.images_imported == 0
    assert report.images_without_label == 1
    assert (project / "images" / "active" / "P001_a.jpg").exists()
    assert not (project / "labels" / "manual" / "P001_a.txt").exists()
    events = read_jsonl(project / "meta" / "status.jsonl")
    assert [(e["img"], e["event"]) for e in events] == [("P001_a.jpg", "uploaded")]


def test_class_out_of_range_goes_to_errors_and_image_not_imported(
    make_project, write_image, write_label, tmp_path
):
    project = make_project()  # 2 classes: valid ids are 0 and 1
    images, labels = tmp_path / "in_images", tmp_path / "in_labels"
    write_image(images / "P001_a.jpg")
    write_image(images / "P002_a.jpg")
    write_label(labels / "P001_a.txt", ["0 0.5 0.5 0.1 0.2"])
    write_label(labels / "P002_a.txt", ["2 0.5 0.5 0.1 0.2"])

    report = import_dataset(project, images, labels, user="marcos", dry_run=False)

    assert report.images_imported == 1
    assert len(report.errors) == 1
    err = report.errors[0]
    assert err.file == "P002_a.txt"
    assert err.line == 1
    assert "out of range" in err.message
    assert (project / "images" / "active" / "P001_a.jpg").exists()
    assert not (project / "images" / "active" / "P002_a.jpg").exists()
    events = read_jsonl(project / "meta" / "status.jsonl")
    assert [e["img"] for e in events] == ["P001_a.jpg"]


def test_wrong_column_count_goes_to_errors(make_project, write_image, write_label, tmp_path):
    project = make_project()
    images, labels = tmp_path / "in_images", tmp_path / "in_labels"
    write_image(images / "P001_a.jpg")
    write_label(labels / "P001_a.txt", ["0 0.5 0.5 0.2"])

    report = import_dataset(project, images, labels, user="marcos", dry_run=True)

    assert report.images_imported == 0
    assert len(report.errors) == 1
    assert "5 columns" in report.errors[0].message


def test_imported_label_is_canonicalized_to_six_decimals(
    make_project, write_image, write_label, tmp_path
):
    project = make_project()
    images, labels = tmp_path / "in_images", tmp_path / "in_labels"
    write_image(images / "P001_a.jpg")
    write_label(labels / "P001_a.txt", ["1 0.5 0.25 0.123456789 1"])

    import_dataset(project, images, labels, user="marcos", dry_run=False)

    label_out = (project / "labels" / "manual" / "P001_a.txt").read_text(encoding="utf-8")
    assert label_out == "1 0.500000 0.250000 0.123457 1.000000\n"


def test_images_are_hardlinked_by_default(make_project, write_image, write_label, tmp_path):
    project = make_project()
    images, labels = tmp_path / "in_images", tmp_path / "in_labels"
    src = write_image(images / "P001_a.jpg")
    write_label(labels / "P001_a.txt", ["0 0.5 0.5 0.1 0.2"])

    import_dataset(project, images, labels, user="marcos", dry_run=False)

    dst = project / "images" / "active" / "P001_a.jpg"
    assert os.stat(src).st_ino == os.stat(dst).st_ino


def test_copy_flag_copies_instead_of_linking(make_project, write_image, write_label, tmp_path):
    project = make_project()
    images, labels = tmp_path / "in_images", tmp_path / "in_labels"
    src = write_image(images / "P001_a.jpg")
    write_label(labels / "P001_a.txt", ["0 0.5 0.5 0.1 0.2"])

    import_dataset(project, images, labels, user="marcos", copy=True, dry_run=False)

    dst = project / "images" / "active" / "P001_a.jpg"
    assert os.stat(src).st_ino != os.stat(dst).st_ino
    assert src.read_bytes() == dst.read_bytes()


def test_non_images_ignored_and_uppercase_ext_accepted(
    make_project, write_image, write_label, tmp_path
):
    project = make_project()
    images, labels = tmp_path / "in_images", tmp_path / "in_labels"
    write_image(images / "P001_a.JPG")
    (images / "notes.txt").write_text("not an image", encoding="utf-8")
    write_label(labels / "P001_a.txt", ["0 0.5 0.5 0.1 0.2"])

    report = import_dataset(project, images, labels, user="marcos", dry_run=False)

    assert report.images_total == 1
    assert (project / "images" / "active" / "P001_a.JPG").exists()
    assert not (project / "images" / "active" / "notes.txt").exists()


def test_empty_label_file_imports_as_done_with_zero_boxes(
    make_project, write_image, write_label, tmp_path
):
    project = make_project()
    images, labels = tmp_path / "in_images", tmp_path / "in_labels"
    write_image(images / "P001_a.jpg")
    write_label(labels / "P001_a.txt", [])

    report = import_dataset(project, images, labels, user="marcos", dry_run=False)

    assert report.images_imported == 1
    assert report.boxes_total == 0
    events = read_jsonl(project / "meta" / "status.jsonl")
    assert events[0]["event"] == "imported"
    assert events[0]["n_boxes"] == 0


def test_source_dir_with_subdirectories_ignores_nested(make_project, write_image, tmp_path):
    project = make_project()
    images, labels = tmp_path / "in_images", tmp_path / "in_labels"
    labels.mkdir()
    write_image(images / "nested" / "P001_a.jpg")

    report = import_dataset(project, images, labels, user="marcos", dry_run=True)

    assert report.images_total == 0
