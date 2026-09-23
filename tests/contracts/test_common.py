"""Contract tests for atomic writes and append-only JSONL logs."""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

from annotation_platform.contracts.common import (
    append_jsonl,
    atomic_write_json,
    atomic_write_text,
    read_jsonl,
)


def test_atomic_write_text_creates_parents(tmp_path) -> None:
    target = tmp_path / "a" / "b" / "file.txt"
    atomic_write_text(target, "hello")
    assert target.read_text() == "hello"


def test_atomic_write_leaves_no_tmp_files(tmp_path) -> None:
    target = tmp_path / "file.txt"
    atomic_write_text(target, "data")
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "file.txt"]
    assert leftovers == []


def test_atomic_write_cleans_tmp_on_failure(tmp_path, monkeypatch) -> None:
    target = tmp_path / "file.txt"

    def boom(_src: str, _dst: str) -> None:
        raise RuntimeError("crash before rename")

    monkeypatch.setattr(os, "replace", boom)
    with contextlib.suppress(RuntimeError):
        atomic_write_text(target, "data")
    assert not target.exists()
    assert [p.name for p in tmp_path.iterdir()] == []


def test_atomic_write_json_roundtrip(tmp_path) -> None:
    target = tmp_path / "d.json"
    atomic_write_json(target, {"a": 1, "b": ["x"]})
    assert json.loads(target.read_text()) == {"a": 1, "b": ["x"]}


def test_append_jsonl_accumulates(tmp_path) -> None:
    log = tmp_path / "log.jsonl"
    append_jsonl(log, {"n": 1})
    append_jsonl(log, {"n": 2})
    assert read_jsonl(log) == [{"n": 1}, {"n": 2}]


def test_read_jsonl_missing_file(tmp_path) -> None:
    assert read_jsonl(tmp_path / "missing.jsonl") == []


def test_read_jsonl_reports_bad_line(tmp_path) -> None:
    log = Path(tmp_path / "log.jsonl")
    log.write_text('{"ok": 1}\nbroken\n')
    try:
        read_jsonl(log)
    except ValueError as exc:
        assert ":2:" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
