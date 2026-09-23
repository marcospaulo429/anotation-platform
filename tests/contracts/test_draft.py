"""Contract tests for draft JSON (PREANNOTATION_PLATFORM.md section 4.2)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from annotation_platform.contracts.draft import DraftBox, DraftDoc

# Literal example from PREANNOTATION_PLATFORM.md section 4.2
DRAFT_EXAMPLE: dict = {
    "schema_version": 1,
    "image": "P0012.jpg",
    "base_version": "sha256-do-estado-carregado",
    "updated_at": "2026-09-23T14:32:07",
    "updated_by": "marcos",
    "ops_since_commit": 7,
    "tiles_seen": [0, 1, 2, 3, 4, 5],
    "boxes": [
        {
            "id": "uuid-v4",
            "cls": 0,
            "cx": 0.5123,
            "cy": 0.3312,
            "w": 0.0210,
            "h": 0.0365,
            "origin": "model",
            "model_conf": 0.83,
            "edited": True,
            "edit_ops": ["move", "resize"],
        },
        {
            "id": "uuid-v4",
            "cls": 3,
            "cx": 0.1011,
            "cy": 0.8020,
            "w": 0.0190,
            "h": 0.0330,
            "origin": "human",
            "edited": True,
            "edit_ops": ["create"],
        },
    ],
    "history": [{"t": "2026-09-23T14:31:50", "op": "resize", "box": "uuid-v4"}],
}


def test_md_example_is_valid() -> None:
    doc = DraftDoc.model_validate(DRAFT_EXAMPLE)
    assert doc.ops_since_commit == 7
    assert doc.boxes[0].origin == "model"
    assert doc.boxes[0].model_conf == 0.83
    assert doc.boxes[1].origin == "human"


def test_box_coordinates_bounded() -> None:
    base = {"id": "b1", "cls": 0, "origin": "human"}
    with pytest.raises(ValidationError):
        DraftBox(**base, cx=1.2, cy=0.5, w=0.1, h=0.1)
    with pytest.raises(ValidationError):
        DraftBox(**base, cx=0.5, cy=0.5, w=0.0, h=0.1)
    with pytest.raises(ValidationError):
        DraftBox(**base, cx=0.5, cy=0.5, w=0.1, h=1.5)


def test_negative_cls_rejected() -> None:
    with pytest.raises(ValidationError):
        DraftBox(id="b1", cls=-1, cx=0.5, cy=0.5, w=0.1, h=0.1, origin="human")


def test_human_box_cannot_carry_model_conf() -> None:
    with pytest.raises(ValidationError, match="model_conf"):
        DraftBox(id="b1", cls=0, cx=0.5, cy=0.5, w=0.1, h=0.1, origin="human", model_conf=0.9)


def test_unknown_edit_op_rejected() -> None:
    with pytest.raises(ValidationError):
        DraftBox(
            id="b1",
            cls=0,
            cx=0.5,
            cy=0.5,
            w=0.1,
            h=0.1,
            origin="human",
            edit_ops=["explode"],  # type: ignore[list-item]
        )


def test_unknown_schema_version_rejected() -> None:
    doc = {**DRAFT_EXAMPLE, "schema_version": 2}
    with pytest.raises(ValidationError, match="schema_version"):
        DraftDoc.model_validate(doc)


def test_tiles_seen_non_negative() -> None:
    doc = {**DRAFT_EXAMPLE, "tiles_seen": [0, -1]}
    with pytest.raises(ValidationError, match="tiles_seen"):
        DraftDoc.model_validate(doc)


def test_json_roundtrip() -> None:
    doc = DraftDoc.model_validate(DRAFT_EXAMPLE)
    assert DraftDoc.model_validate(doc.model_dump(mode="json")) == doc
