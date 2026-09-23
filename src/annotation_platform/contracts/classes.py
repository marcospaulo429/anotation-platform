"""Class-list rules (frozen 2026-09-23).

- Initial classes come from the creation source: checkpoint model.names
  (pre-annotation), user input (manual), or label file (import).
- Afterwards the list is APPEND-ONLY: add at the end, any time (Classes page
  or inline in the canvas); never reorder/rename/remove.
- Swapping the pre-annotation checkpoint requires the new model.names to be a
  PREFIX of the project's classes (otherwise: different classes -> new project).
"""

from __future__ import annotations


class ClassListError(ValueError):
    """Raised on any violation of the append-only class rules."""


def add_class(classes: list[str], name: str) -> list[str]:
    """Append a new class at the END of the list. Returns a new list.

    Reorder/rename/remove is not representable through this function on
    purpose — the API layer must not offer it.
    """
    name = name.strip()
    if not name:
        raise ClassListError("class name must be non-empty")
    if name in classes:
        raise ClassListError(f"class {name!r} already exists (index {classes.index(name)})")
    return [*classes, name]


def check_checkpoint_compatible(model_names: list[str], project_classes: list[str]) -> None:
    """Validate that a checkpoint's classes are a prefix of the project's.

    The model emits class indices 0..N-1; those indices must mean the same
    thing in the project. Extra project classes (added later by humans) sit
    after index N-1 and are never emitted by the model — that is allowed.
    """
    if len(model_names) > len(project_classes):
        raise ClassListError(
            f"checkpoint has {len(model_names)} classes but project has only "
            f"{len(project_classes)}; model indices would be out of range"
        )
    for idx, name in enumerate(model_names):
        if project_classes[idx] != name:
            raise ClassListError(
                f"checkpoint class {idx} is {name!r} but project class {idx} is "
                f"{project_classes[idx]!r}; reordering is a silent YOLO index bug"
            )


def initial_classes_from_checkpoint(model_names: list[str]) -> list[str]:
    """Classes for a project created with pre-annotation: model.names verbatim."""
    if not model_names:
        raise ClassListError("checkpoint exposes no class names")
    return list(model_names)
