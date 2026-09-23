"""status.jsonl contract (PREANNOTATION_PLATFORM.md section 4.4).

Append-only event log: one event per line. The current status of an image is
its LAST event — rebuildable by scanning the file (cacheable in SQLite later).
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .common import append_jsonl, read_jsonl


class EventType(StrEnum):
    UPLOADED = "uploaded"
    IMPORTED = "imported"
    PRELABELED = "prelabeled"
    PREANNOTATE_FAILED = "preannotate_failed"
    DRAFT_SAVED = "draft_saved"
    DRAFT_COMMITTED = "draft_committed"
    DONE = "done"
    REOPENED = "reopened"
    REVERTED = "reverted"
    EXPORTED = "exported"
    CLASS_ADDED = "class_added"


class StatusEvent(BaseModel):
    """One line of meta/status.jsonl. Extra keys (ops, n_boxes, ...) allowed."""

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    t: str
    img: str = Field(min_length=1)
    event: EventType
    user: str = Field(min_length=1)


def append_event(path: Path | str, event: StatusEvent) -> None:
    """Append an event to the status log (append-only, fsync'd)."""
    append_jsonl(path, event.model_dump(mode="json"))


def current_status(path: Path | str) -> dict[str, StatusEvent]:
    """Rebuild current status per image: img -> its last event."""
    latest: dict[str, StatusEvent] = {}
    for record in read_jsonl(path):
        event = StatusEvent.model_validate(record)
        latest[event.img] = event
    return latest
