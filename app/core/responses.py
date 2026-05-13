from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def api_success(
    data: Any = None,
    *,
    message: str = "",
    status_code: int = 200,
) -> JSONResponse:
    payload = {
        "message": message,
        "data": data,
        "status": True,
    }
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))
