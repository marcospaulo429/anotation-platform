"""Streaming sha256 + checkpoint validation tests (no torch)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from annotation_platform.contracts.project import PreannotationConfig
from annotation_platform.engine.checkpoint import (
    CHUNK_SIZE,
    CheckpointMismatchError,
    sha256_file,
    verified_checkpoint_sha256,
)


def test_sha256_file_matches_hashlib_small(tmp_path: Path) -> None:
    payload = b"hello-checkpoint" * 100
    target = tmp_path / "small.pt"
    target.write_bytes(payload)
    assert sha256_file(target) == hashlib.sha256(payload).hexdigest()


def test_sha256_file_crosses_chunk_boundary(tmp_path: Path) -> None:
    payload = b"x" * (CHUNK_SIZE + 123)  # forces a second streaming chunk
    target = tmp_path / "big.pt"
    target.write_bytes(payload)
    assert sha256_file(target) == hashlib.sha256(payload).hexdigest()


def test_verified_returns_computed_when_field_absent(tmp_path: Path) -> None:
    target = tmp_path / "m.pt"
    target.write_bytes(b"weights")
    cfg = PreannotationConfig(checkpoint=str(target))
    assert verified_checkpoint_sha256(cfg) == hashlib.sha256(b"weights").hexdigest()


def test_verified_ok_when_declared_matches(tmp_path: Path) -> None:
    target = tmp_path / "m.pt"
    target.write_bytes(b"weights")
    cfg = PreannotationConfig(
        checkpoint=str(target), checkpoint_sha256=hashlib.sha256(b"weights").hexdigest()
    )
    assert verified_checkpoint_sha256(cfg) == hashlib.sha256(b"weights").hexdigest()


def test_verified_mismatch_raises(tmp_path: Path) -> None:
    target = tmp_path / "m.pt"
    target.write_bytes(b"weights")
    cfg = PreannotationConfig(checkpoint=str(target), checkpoint_sha256="0" * 64)
    with pytest.raises(CheckpointMismatchError, match="sha256 mismatch"):
        verified_checkpoint_sha256(cfg)


def test_verified_missing_file_raises(tmp_path: Path) -> None:
    cfg = PreannotationConfig(checkpoint=str(tmp_path / "nope.pt"))
    with pytest.raises(FileNotFoundError, match="checkpoint not found"):
        verified_checkpoint_sha256(cfg)


def test_verified_without_checkpoint_raises() -> None:
    cfg = PreannotationConfig(enabled=False)
    with pytest.raises(ValueError, match="checkpoint is not set"):
        verified_checkpoint_sha256(cfg)
