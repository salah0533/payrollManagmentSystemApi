from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core.localization import translate


def api_success(
    data: Any = None,
    *,
    message: str = "",
    message_key: str | None = None,
    message_params: dict[str, Any] | None = None,
    status_code: int = 200,
) -> JSONResponse:
    resolved_message = translate(message_key, message_params, fallback=message) if message_key else message
    payload = {
        "message": resolved_message,
        "data": data,
        "status": True,
    }
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))
