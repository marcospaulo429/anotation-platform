"""Contract tests for YOLO label parsing/serialization."""

from __future__ import annotations

import pytest

from annotation_platform.contracts.yolo import (
    YoloLine,
    YoloValidationError,
    dump_yolo_text,
    parse_yolo_file,
    parse_yolo_text,
)


def test_parse_valid_lines() -> None:
    lines = parse_yolo_text("0 0.512300 0.331200 0.021000 0.036500\n3 0.101 0.802 0.019 0.033\n")
    assert lines[0].cls == 0
    assert lines[1].w == 0.019


def test_blank_lines_and_empty_file_ok() -> None:
    assert parse_yolo_text("") == []
    assert parse_yolo_text("\n  \n") == []


def test_wrong_column_count_rejected_with_lineno() -> None:
    with pytest.raises(YoloValidationError, match="line 2"):
        parse_yolo_text("0 0.5 0.5 0.1 0.1\n0 0.5 0.5 0.1\n")


def test_class_must_be_plain_integer() -> None:
    with pytest.raises(YoloValidationError, match="line 1"):
        parse_yolo_text("0.0 0.5 0.5 0.1 0.1")
    with pytest.raises(YoloValidationError, match="line 1"):
        parse_yolo_text("MD 0.5 0.5 0.1 0.1")


def test_class_out_of_range_rejected_when_n_classes() -> None:
    with pytest.raises(YoloValidationError, match="out of range"):
        parse_yolo_text("7 0.5 0.5 0.1 0.1", n_classes=7)
    # in range ok
    parse_yolo_text("6 0.5 0.5 0.1 0.1", n_classes=7)


def test_coordinates_bounded() -> None:
    with pytest.raises(YoloValidationError, match="line 1"):
        parse_yolo_text("0 1.2 0.5 0.1 0.1")
    with pytest.raises(YoloValidationError, match="line 1"):
        parse_yolo_text("0 0.5 0.5 0.0 0.1")


def test_serialization_uses_six_decimal_grid() -> None:
    text = dump_yolo_text([YoloLine(cls=0, cx=0.5123, cy=0.3312, w=0.021, h=0.0365)])
    assert text == "0 0.512300 0.331200 0.021000 0.036500\n"


def test_roundtrip_idempotent() -> None:
    src = "0 0.512300 0.331200 0.021000 0.036500\n3 0.101100 0.802000 0.019000 0.033000\n"
    once = dump_yolo_text(parse_yolo_text(src))
    twice = dump_yolo_text(parse_yolo_text(once))
    assert once == src
    assert twice == once


def test_parse_file(tmp_path) -> None:
    p = tmp_path / "img.txt"
    p.write_text("0 0.5 0.5 0.1 0.1\n", encoding="utf-8")
    assert len(parse_yolo_file(p, n_classes=1)) == 1
