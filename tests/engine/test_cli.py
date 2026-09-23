"""CLI tests (dry-run paths only: no torch/ultralytics imported)."""

from __future__ import annotations

from pathlib import Path

import pytest

from annotation_platform.engine.cli import main


def test_dry_run_writes_nothing(project_root: Path, capsys: pytest.CaptureFixture) -> None:
    code = main(["--project", str(project_root), "--dry-run"])
    assert code == 0
    out = capsys.readouterr().out
    assert "[dry-run]" in out
    assert not (project_root / "labels").exists()
    assert not (project_root / "meta").exists()


def test_help_works(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "--project" in capsys.readouterr().out


def test_project_arg_is_required() -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_dry_run_with_images_sublist(project_root: Path, capsys: pytest.CaptureFixture) -> None:
    code = main(["--project", str(project_root), "--dry-run", "--images", "b.jpg"])
    assert code == 0
    out = capsys.readouterr().out
    assert "b.jpg" in out
    assert not (project_root / "labels").exists()


@pytest.mark.skip(reason="validação manual em CPU pelo orquestrador")
def test_real_ultralytics_predictor_on_cpu() -> None:
    """Integration: UltralyticsPredictor over a real checkpoint + image (CPU)."""
