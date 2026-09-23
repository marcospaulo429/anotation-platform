"""Factory da app FastAPI + entry point do script ``annotate-api``."""

from __future__ import annotations

from fastapi import FastAPI

from . import classes, images, import_export, jobs, labels, projects, stats
from .config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Cria a app. Falha no startup se API_KEY não estiver configurada.

    root_path vem de settings para a app ser montável em subpath atrás do
    nginx (ex.: /annotate-api).
    """
    settings = settings or Settings()
    if not settings.api_key:
        raise RuntimeError(
            "API_KEY não configurada: defina a variável de ambiente API_KEY "
            "antes de subir o annotate-api (ver fly_det_api/gen_key.py)."
        )
    app = FastAPI(
        title="annotation-platform-api",
        version="0.1.0",
        root_path=settings.root_path,
    )
    app.state.settings = settings

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for module in (projects, classes, images, labels, import_export, jobs, stats):
        app.include_router(module.router, prefix="/annotate")
    return app


def main() -> None:
    """Entry point do script ``annotate-api`` (uvicorn)."""
    import uvicorn

    settings = Settings()
    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port)
