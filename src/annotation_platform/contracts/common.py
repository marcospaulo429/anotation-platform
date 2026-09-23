"""Shared primitives for the platform contracts.

Global rules implemented here:
- Label/config writes are ALWAYS atomic (tmp file + os.replace).
- JSONL event logs are append-only (O_APPEND + fsync).
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utcnow_iso() -> str:
    """Current UTC time as ISO-8601 seconds precision (contract timestamps)."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def atomic_write_text(path: Path | str, content: str) -> None:
    """Write text to path atomically: tmp file in the same dir + os.replace.

    Prevents corrupted labels/configs if the process dies mid-write.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def atomic_write_json(path: Path | str, data: Any) -> None:
    """Serialize data as JSON and write atomically."""
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def append_jsonl(path: Path | str, record: dict[str, Any]) -> None:
    """Append one JSON line to an append-only log (O_APPEND + fsync)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())


def read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    """Read an append-only JSONL log. Missing file -> empty list."""
    path = Path(path)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSONL line: {exc}") from exc
    return records
