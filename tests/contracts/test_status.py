"""Contract tests for status.jsonl (PREANNOTATION_PLATFORM.md section 4.4)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from annotation_platform.contracts.status import (
    EventType,
    StatusEvent,
    append_event,
    current_status,
)


def _ev(img: str, event: EventType, **extra) -> StatusEvent:
    return StatusEvent(t="2026-09-23T14:32:07", img=img, event=event, user="marcos", **extra)


def test_md_example_line_is_valid() -> None:
    record = {
        "t": "2026-09-23T14:32:07",
        "img": "P0012.jpg",
        "event": "draft_committed",
        "user": "marcos",
        "ops": 7,
        "n_boxes": 14,
    }
    ev = StatusEvent.model_validate(record)
    assert ev.event == EventType.DRAFT_COMMITTED
    assert ev.ops == 7  # extra keys preserved


def test_unknown_event_rejected() -> None:
    with pytest.raises(ValidationError):
        StatusEvent(t="t", img="a.jpg", event="exploded", user="u")


def test_all_contract_events_accepted() -> None:
    for event in EventType:
        StatusEvent(t="t", img="a.jpg", event=event, user="u")


def test_current_status_is_last_event(tmp_path) -> None:
    log = tmp_path / "status.jsonl"
    append_event(log, _ev("a.jpg", EventType.UPLOADED))
    append_event(log, _ev("b.jpg", EventType.UPLOADED))
    append_event(log, _ev("a.jpg", EventType.PRELABELED, n_boxes=12))
    append_event(log, _ev("a.jpg", EventType.DONE, n_boxes=14))

    status = current_status(log)
    assert status["a.jpg"].event == EventType.DONE
    assert status["a.jpg"].n_boxes == 14
    assert status["b.jpg"].event == EventType.UPLOADED


def test_missing_log_is_empty(tmp_path) -> None:
    assert current_status(tmp_path / "nope.jsonl") == {}


def test_corrupt_line_raises_with_lineno(tmp_path) -> None:
    log = tmp_path / "status.jsonl"
    log.write_text('{"t":"t","img":"a","event":"uploaded","user":"u"}\nnot-json\n')
    with pytest.raises(ValueError, match="line 2|2"):
        current_status(log)
