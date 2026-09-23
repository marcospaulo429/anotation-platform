#!/usr/bin/env python3
"""Import an already-annotated YOLO dataset into a platform project.

Thin CLI over ``annotation_platform.dataset_ops.import_dataset``. The default
is a validation DRY-RUN (nothing is written); pass ``--execute`` to write.
Prints the ImportReport as JSON on stdout. Exit code 2 on validation errors.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from annotation_platform.dataset_ops import import_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True, help="project root (project.yaml)")
    parser.add_argument("--images", type=Path, required=True, help="source images directory")
    parser.add_argument("--labels", type=Path, required=True, help="source YOLO labels directory")
    parser.add_argument("--user", default="cli", help="user recorded in status events")
    parser.add_argument(
        "--copy", action="store_true", help="copy images instead of hardlinking"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="actually write (default: dry-run, validate only)",
    )
    args = parser.parse_args(argv)

    report = import_dataset(
        args.project,
        args.images,
        args.labels,
        user=args.user,
        copy=args.copy,
        dry_run=not args.execute,
    )
    print(report.model_dump_json(indent=2))
    return 2 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
