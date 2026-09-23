"""Auth da API: header X-API-Key comparado a settings.api_key.

Padrão de referência: fly_det_api/app/core/security.py. Diferença deliberada:
aqui a chave é OBRIGATÓRIA — create_app recusa subir sem API_KEY configurada.
"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    request: Request,
    x_api_key: str | None = Security(_api_key_header),
) -> None:
    settings = request.app.state.settings
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="X-API-Key header ausente.")
    if not hmac.compare_digest(x_api_key, settings.api_key or ""):
        raise HTTPException(status_code=403, detail="API Key inválida.")
