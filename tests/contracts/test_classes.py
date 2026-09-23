"""Contract tests for class-list rules (append-only, checkpoint prefix)."""

from __future__ import annotations

import pytest

from annotation_platform.contracts.classes import (
    ClassListError,
    add_class,
    check_checkpoint_compatible,
    initial_classes_from_checkpoint,
)

BASE = ["MD", "MV", "MC", "MF"]


def test_add_class_appends_at_end() -> None:
    assert add_class(BASE, "DANO") == ["MD", "MV", "MC", "MF", "DANO"]


def test_add_class_does_not_mutate_input() -> None:
    classes = list(BASE)
    add_class(classes, "DANO")
    assert classes == BASE


def test_add_class_rejects_duplicates() -> None:
    with pytest.raises(ClassListError, match="already exists"):
        add_class(BASE, "MV")


def test_add_class_rejects_empty() -> None:
    with pytest.raises(ClassListError, match="non-empty"):
        add_class(BASE, "   ")


def test_checkpoint_must_be_prefix() -> None:
    check_checkpoint_compatible(["MD", "MV"], BASE)  # subset prefix ok
    check_checkpoint_compatible(BASE, BASE)  # exact ok
    check_checkpoint_compatible(BASE, [*BASE, "DANO"])  # project may have extras


def test_checkpoint_longer_than_project_rejected() -> None:
    with pytest.raises(ClassListError, match="out of range"):
        check_checkpoint_compatible([*BASE, "EXTRA"], BASE)


def test_checkpoint_order_mismatch_rejected() -> None:
    with pytest.raises(ClassListError, match="silent YOLO index bug"):
        check_checkpoint_compatible(["MV", "MD", "MC", "MF"], BASE)


def test_initial_classes_from_checkpoint_verbatim() -> None:
    names = ["MD", "MV", "MC"]
    result = initial_classes_from_checkpoint(names)
    assert result == names
    assert result is not names  # defensive copy


def test_initial_classes_empty_checkpoint_rejected() -> None:
    with pytest.raises(ClassListError, match="no class names"):
        initial_classes_from_checkpoint([])
