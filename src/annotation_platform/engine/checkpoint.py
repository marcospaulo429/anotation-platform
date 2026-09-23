"""Checkpoint provenance helpers: streaming sha256 + validation against project.yaml.

The pre_meta sidecar (contracts.pre_meta.ModelRef) records the sha256 of the
checkpoint that produced the predictions. If project.yaml declares
``preannotation.checkpoint_sha256`` and it diverges from the real file, that
is a hard error (silent model swap = broken provenance).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..contracts.project import PreannotationConfig

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB streaming chunks: checkpoints can be multi-GB


class CheckpointMismatchError(RuntimeError):
    """project.yaml checkpoint_sha256 does not match the real checkpoint file."""


def sha256_file(path: Path | str, chunk_size: int = CHUNK_SIZE) -> str:
    """Streaming sha256 of a file (constant memory, 8 MiB chunks)."""
    path = Path(path)
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verified_checkpoint_sha256(cfg: PreannotationConfig) -> str:
    """Compute the checkpoint sha256, validating the declared hash when present.

    - ``checkpoint_sha256`` set and diverging -> CheckpointMismatchError.
    - field absent -> returns the computed hash (for the pre_meta sidecar).
    """
    if not cfg.checkpoint:
        raise ValueError("preannotation.checkpoint is not set in project.yaml")
    path = Path(cfg.checkpoint)
    if not path.is_file():
        raise FileNotFoundError(f"checkpoint not found: {path}")
    actual = sha256_file(path)
    declared = (cfg.checkpoint_sha256 or "").lower()
    if declared and declared != actual:
        raise CheckpointMismatchError(
            f"checkpoint sha256 mismatch for {path}: project.yaml declares "
            f"{declared}, actual file hashes to {actual}"
        )
    return actual
