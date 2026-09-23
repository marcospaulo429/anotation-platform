"""Orchestration tests with a FAKE predictor (no torch/ultralytics)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from annotation_platform.contracts.common import read_jsonl
from annotation_platform.contracts.pre_meta import PreBox, PreMeta
from annotation_platform.contracts.yolo import parse_yolo_file
from annotation_platform.engine.core import preannotate_project

BOXES = [
    PreBox(cls=0, cx=0.5, cy=0.5, w=0.1, h=0.2, conf=0.9),
    PreBox(cls=1, cx=0.25, cy=0.75, w=0.05, h=0.05, conf=0.42),
]


class FakePredictor:
    def __init__(self, boxes: list[PreBox] | None = None) -> None:
        self.boxes = list(boxes) if boxes is not None else list(BOXES)
        self.calls: list[Path] = []

    def __call__(self, image_path: Path) -> list[PreBox]:
        self.calls.append(Path(image_path))
        return list(self.boxes)


def test_writes_pre_txt_meta_and_event(project_root: Path) -> None:
    summary = preannotate_project(project_root, FakePredictor(), user="tester")

    assert summary.processed == ["a.jpg", "b.jpg"]
    assert summary.skipped == []
    assert summary.failed == {}

    # labels/pre/<stem>.txt: valid YOLO, no confidence column
    txt_path = project_root / "labels" / "pre" / "a.txt"
    lines = parse_yolo_file(txt_path, n_classes=2)
    assert len(lines) == 2
    assert (lines[0].cls, lines[0].cx) == (0, pytest.approx(0.5))
    for raw in txt_path.read_text(encoding="utf-8").splitlines():
        assert len(raw.split()) == 5  # YOLO has no room for confidence

    # labels/pre_meta/<stem>.json: valid against the contract, keeps conf
    meta = PreMeta.model_validate(
        json.loads((project_root / "labels" / "pre_meta" / "a.json").read_text(encoding="utf-8"))
    )
    assert meta.image == "a.jpg"
    assert meta.engine == "sahi"
    assert meta.params.slice == 640
    assert len(meta.model.sha256) == 64
    assert [b.conf for b in meta.boxes] == [0.9, 0.42]
    assert meta.inference_seconds >= 0.0

    # meta/status.jsonl: one prelabeled event per image
    events = read_jsonl(project_root / "meta" / "status.jsonl")
    assert [e["event"] for e in events] == ["prelabeled", "prelabeled"]
    assert {e["img"] for e in events} == {"a.jpg", "b.jpg"}
    assert all(e["user"] == "tester" for e in events)
    assert events[0]["n_boxes"] == 2


def test_skips_existing_and_force_redoes(project_root: Path) -> None:
    predictor = FakePredictor()
    preannotate_project(project_root, predictor)
    assert len(predictor.calls) == 2

    summary = preannotate_project(project_root, predictor)
    assert summary.processed == []
    assert summary.skipped == ["a.jpg", "b.jpg"]
    assert len(predictor.calls) == 2  # predictor not called again

    summary = preannotate_project(project_root, predictor, force=True)
    assert summary.processed == ["a.jpg", "b.jpg"]
    assert len(predictor.calls) == 4


def test_images_sublist_and_missing_image_errors(project_root: Path) -> None:
    predictor = FakePredictor()
    summary = preannotate_project(project_root, predictor, images=["b.jpg"])
    assert summary.processed == ["b.jpg"]
    assert [p.name for p in predictor.calls] == ["b.jpg"]
    assert not (project_root / "labels" / "pre" / "a.txt").exists()

    with pytest.raises(FileNotFoundError, match="nope.jpg"):
        preannotate_project(project_root, FakePredictor(), images=["nope.jpg"])


def test_dry_run_writes_nothing(project_root: Path) -> None:
    predictor = FakePredictor()
    summary = preannotate_project(project_root, predictor, dry_run=True)

    assert summary.dry_run is True
    assert summary.processed == ["a.jpg", "b.jpg"]  # the plan
    assert predictor.calls == []  # predictor never invoked
    assert not (project_root / "labels").exists()
    assert not (project_root / "meta").exists()


def test_dry_run_marks_existing_as_skipped(project_root: Path) -> None:
    preannotate_project(project_root, FakePredictor(), images=["a.jpg"])
    summary = preannotate_project(project_root, None, dry_run=True)
    assert summary.processed == ["b.jpg"]
    assert summary.skipped == ["a.jpg"]


def test_failed_image_logs_event_and_continues(project_root: Path) -> None:
    class FlakyPredictor:
        def __call__(self, image_path: Path) -> list[PreBox]:
            if image_path.name == "a.jpg":
                raise RuntimeError("boom")
            return list(BOXES)

    summary = preannotate_project(project_root, FlakyPredictor())
    assert summary.processed == ["b.jpg"]
    assert list(summary.failed) == ["a.jpg"]

    events = read_jsonl(project_root / "meta" / "status.jsonl")
    by_img = {e["img"]: e for e in events}
    assert by_img["a.jpg"]["event"] == "preannotate_failed"
    assert "boom" in by_img["a.jpg"]["error"]
    assert by_img["b.jpg"]["event"] == "prelabeled"


def test_out_of_range_class_marks_failed(project_root: Path) -> None:
    bad = [PreBox(cls=7, cx=0.5, cy=0.5, w=0.1, h=0.1, conf=0.5)]
    summary = preannotate_project(project_root, FakePredictor(bad))
    assert summary.processed == []
    assert set(summary.failed) == {"a.jpg", "b.jpg"}
    assert not (project_root / "labels").exists()


def test_predictor_required_unless_dry_run(project_root: Path) -> None:
    with pytest.raises(ValueError, match="predictor"):
        preannotate_project(project_root, None)
