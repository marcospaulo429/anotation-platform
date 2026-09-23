"""Settings da API de anotação (pydantic-settings), no padrão do fly_det_api."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração do serviço annotate-api.

    - api_key: chave exigida no header ``X-API-Key`` (env ``API_KEY``).
      Obrigatória: ``create_app`` falha no startup se ausente.
    - annotate_root: raiz dos dados da plataforma (env ``ANNOTATE_ROOT``);
      projetos ficam em ``<annotate_root>/projects/<slug>`` e o cache derivado
      em ``<annotate_root>/.cache/``.
    """

    api_key: str | None = Field(default=None, alias="API_KEY")
    annotate_root: Path = Field(
        default=Path("/raid/user_marcospaulo/annotate"), alias="ANNOTATE_ROOT"
    )
    host: str = Field(default="0.0.0.0", alias="ANNOTATE_API_HOST")
    port: int = Field(default=5200, alias="ANNOTATE_API_PORT")
    root_path: str = Field(default="", alias="ANNOTATE_ROOT_PATH")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )
