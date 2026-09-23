"""Factory da app FastAPI + entry point do script ``annotate-api``."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import classes, images, import_export, jobs, labels, projects, stats
from .config import Settings


class NoCacheStaticFiles(StaticFiles):
    """StaticFiles sem cache: o SPA é servido pela mesma app em dev e o
    navegador cacheia módulos ES agressivamente por URL. Em produção o nginx
    pode sobrepor cache explícito."""

    async def get_response(self, path: str, scope):  # type: ignore[override]
        resp: Response = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-store"
        return resp


def _resolve_web_dir(settings: Settings) -> Path | None:
    """Localiza o diretório do SPA (web/). None se não existir."""
    if settings.web_dir is not None:
        return settings.web_dir if settings.web_dir.is_dir() else None
    module = Path(__file__).resolve()
    for candidate in (module.parents[1] / "web", module.parents[3] / "web"):
        if (candidate / "index.html").is_file():
            return candidate
    return None


def create_app(settings: Settings | None = None) -> FastAPI:
    """Cria a app. Falha no startup se API_KEY não estiver configurada.

    root_path vem de settings para a app ser montável em subpath atrás do
    nginx (ex.: /annotate-api).
    """
    settings = settings or Settings()
    if not settings.api_key:
        raise RuntimeError(
            "API_KEY não configurada: defina a variável de ambiente API_KEY "
            "antes de subir o annotate-api."
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
    app.include_router(images.media_router, prefix="/annotate")

    # SPA estático por último: captura só o que não casou nas rotas acima.
    web_dir = _resolve_web_dir(settings)
    if web_dir is not None:
        app.mount("/", NoCacheStaticFiles(directory=web_dir, html=True), name="web")
    return app


def main() -> None:
    """Entry point do script ``annotate-api`` (uvicorn)."""
    import uvicorn

    settings = Settings()
    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port)
