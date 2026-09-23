"""Auth da API: header X-API-Key comparado a settings.api_key.

Padrão de referência: fly_det_api/app/core/security.py. Diferença deliberada:
aqui a chave é OBRIGATÓRIA — create_app recusa subir sem API_KEY configurada.
"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader, APIKeyQuery

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_api_key_query = APIKeyQuery(name="api_key", auto_error=False)


def _check(settings, provided: str | None) -> None:
    if provided is None:
        raise HTTPException(status_code=401, detail="X-API-Key header ausente.")
    if not hmac.compare_digest(provided, settings.api_key or ""):
        raise HTTPException(status_code=403, detail="API Key inválida.")


async def verify_api_key(
    request: Request,
    x_api_key: str | None = Security(_api_key_header),
) -> None:
    _check(request.app.state.settings, x_api_key)


async def verify_api_key_or_query(
    request: Request,
    x_api_key: str | None = Security(_api_key_header),
    api_key: str | None = Security(_api_key_query),
) -> None:
    """Auth para endpoints GET de mídia (thumb/tiles/full).

    ``<img>`` e o loader de tiles do canvas não enviam headers, então a chave
    pode vir por query param (``?api_key=``). Uso RESTRITO a esses endpoints —
    nunca em rotas que alteram estado.
    """
    _check(request.app.state.settings, x_api_key or api_key)
