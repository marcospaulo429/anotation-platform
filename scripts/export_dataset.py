#!/usr/bin/env python3
"""Freeze an immutable training snapshot (exports/vN) of a platform project.

Thin CLI over ``annotation_platform.dataset_ops.export_dataset``. The split is
ALWAYS by plate (never random per image). Prints the ExportManifest as JSON.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from annotation_platform.dataset_ops import export_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True, help="project root (project.yaml)")
    parser.add_argument("--user", required=True, help="who is exporting (manifest + status event)")
    args = parser.parse_args(argv)

    manifest = export_dataset(args.project, user=args.user)
    print(manifest.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
