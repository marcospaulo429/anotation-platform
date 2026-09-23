"""Regressão do bug de save (2026-09-23): history do canvas usa box_id e
meta-ops undo/redo — o contrato não pode rejeitar esses drafts."""

from __future__ import annotations

from annotation_platform.contracts.draft import DraftDoc, HistoryEvent

BASE: dict = {
    "schema_version": 1,
    "image": "P0001.jpg",
    "base_version": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "updated_at": "2026-09-23T19:00:00",
    "updated_by": "marcos",
    "ops_since_commit": 2,
    "tiles_seen": [],
    "boxes": [],
}


def test_history_accepts_box_null() -> None:
    """Ops sem caixa (ou box_id ausente no cliente) gravam box=null."""
    ev = HistoryEvent(t="2026-09-23T19:00:00", op="create", box=None)
    assert ev.box is None


def test_history_accepts_undo_redo() -> None:
    for op in ("undo", "redo"):
        ev = HistoryEvent(t="2026-09-23T19:00:00", op=op, box=None)
        assert ev.op == op


def test_draft_with_canvas_style_history_is_valid() -> None:
    """Payload exato que o SPA monta após criar uma caixa e desfazer."""
    doc = DraftDoc.model_validate(
        {
            **BASE,
            "history": [
                {"t": "2026-09-23T19:00:01", "op": "create", "box": "abc-123"},
                {"t": "2026-09-23T19:00:05", "op": "undo", "box": None},
            ],
        }
    )
    assert len(doc.history) == 2
    assert doc.history[1].box is None
