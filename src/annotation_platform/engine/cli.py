"""CLI entry point ``annotate-engine``: batch pre-annotation of a project.

Examples:
    annotate-engine --project /raid/user_marcospaulo/annotate/projects/placas-2026-q4
    annotate-engine --project DIR --images IMG_001.jpg IMG_002.jpg
    annotate-engine --project DIR --force --dry-run
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..contracts.project import load_project
from .core import preannotate_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="annotate-engine",
        description=(
            "Batch pre-annotation: YOLO predict (plain or SAHI) over images/active/, "
            "writing labels/pre/ + labels/pre_meta/ + meta/status.jsonl."
        ),
    )
    parser.add_argument(
        "--project",
        required=True,
        type=Path,
        help="Project root (directory containing project.yaml).",
    )
    parser.add_argument(
        "--images",
        nargs="+",
        default=None,
        metavar="NAME",
        help="Image names within images/active/ to process (default: all).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-pre-annotate images that already have labels/pre/<stem>.txt.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only list what would be done; writes nothing, loads no model.",
    )
    parser.add_argument(
        "--user",
        default="engine",
        help="Value for the 'user' field of status events (default: engine).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root: Path = args.project

    predictor = None
    if not args.dry_run:
        # Heavy deps (torch/ultralytics via fly_det) load lazily, CPU-forced,
        # and the checkpoint weights only on the first image.
        from .predict import UltralyticsPredictor

        cfg = load_project(root / "project.yaml")
        predictor = UltralyticsPredictor.from_config(cfg.preannotation)

    summary = preannotate_project(
        root,
        predictor,
        images=args.images,
        force=args.force,
        user=args.user,
        dry_run=args.dry_run,
    )

    mode = "[dry-run] " if summary.dry_run else ""
    print(
        f"{mode}processed: {len(summary.processed)}  "
        f"skipped: {len(summary.skipped)}  failed: {len(summary.failed)}"
    )
    for name in summary.processed:
        print(f"  [ok]   {name}")
    for name in summary.skipped:
        print(f"  [skip] {name}")
    for name, err in summary.failed.items():
        print(f"  [fail] {name}: {err}")
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
