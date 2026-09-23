"""Dataset operations shared by the API routes and the CLI scripts.

This package is the SINGLE implementation of import/export logic:
- `api/` routes are thin HTTP wrappers over these functions;
- `scripts/` CLIs are thin argparse wrappers over these functions.

Interface frozen by the orchestrator (2026-09-23); implemented by anno-data.
"""

from .exporter import ExportManifest, export_dataset
from .importer import FileImportError, ImportReport, import_dataset

__all__ = [
    "ExportManifest",
    "FileImportError",
    "ImportReport",
    "export_dataset",
    "import_dataset",
]
