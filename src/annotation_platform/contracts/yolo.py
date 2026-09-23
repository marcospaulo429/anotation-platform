"""YOLO label file parsing/serialization with contract validation.

Format per line: ``class cx cy w h`` (normalized). Used by import (validating
external labels) and commit (writing labels/manual/*.txt).

Note: strict overlap/canonicalization arithmetic lives in fly_det
(fly_det.utils.yolo_utils / overlap_filter) and is reused by the engine —
this module only guarantees structural validity of the TXT.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class YoloLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cls: int = Field(ge=0)
    cx: float = Field(ge=0.0, le=1.0)
    cy: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)

    def to_text(self) -> str:
        """Serialize with the canonical six-decimal grid (repo convention)."""
        return f"{self.cls} {self.cx:.6f} {self.cy:.6f} {self.w:.6f} {self.h:.6f}"


class YoloValidationError(ValueError):
    """One invalid line in a YOLO label file."""

    def __init__(self, line_no: int, message: str):
        self.line_no = line_no
        super().__init__(f"line {line_no}: {message}")


def parse_yolo_text(text: str, n_classes: int | None = None) -> list[YoloLine]:
    """Parse and validate a YOLO label file.

    Args:
        text: file contents.
        n_classes: if given, every class id must be < n_classes (import rule:
            ids out of range are an error, never silently dropped).

    Raises:
        YoloValidationError: with the 1-based line number of the first problem.
    """
    lines: list[YoloLine] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) != 5:
            raise YoloValidationError(line_no, f"expected 5 columns, got {len(parts)}")
        try:
            cls = int(parts[0])
        except ValueError:
            raise YoloValidationError(line_no, f"class id {parts[0]!r} is not an integer") from None
        if str(cls) != parts[0] and not (parts[0].startswith("+") and str(cls) == parts[0][1:]):
            raise YoloValidationError(line_no, f"class id {parts[0]!r} is not a plain integer")
        if n_classes is not None and cls >= n_classes:
            raise YoloValidationError(
                line_no, f"class id {cls} out of range (project has {n_classes} classes)"
            )
        try:
            cx, cy, w, h = (float(p) for p in parts[1:])
        except ValueError:
            raise YoloValidationError(line_no, "coordinates must be floats") from None
        try:
            lines.append(YoloLine(cls=cls, cx=cx, cy=cy, w=w, h=h))
        except ValueError as exc:
            raise YoloValidationError(line_no, str(exc)) from None
    return lines


def parse_yolo_file(path: Path | str, n_classes: int | None = None) -> list[YoloLine]:
    """Parse and validate a YOLO .txt label file."""
    with open(path, encoding="utf-8") as fh:
        return parse_yolo_text(fh.read(), n_classes=n_classes)


def dump_yolo_text(lines: list[YoloLine]) -> str:
    """Serialize boxes to YOLO text (six-decimal canonical grid)."""
    return "".join(line.to_text() + "\n" for line in lines)
