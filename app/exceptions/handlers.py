from __future__ import annotations

import logging
from collections.abc import Iterable
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.exceptions.base_exception import AppException, DatabaseException, InternalServerException


logger = logging.getLogger("app.errors")


def _json_response(payload: dict[str, Any], *, status_code: int, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload), headers=headers)


def _status_phrase(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Request failed"


def _error_code_from_status(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).name.lower()
    except ValueError:
        return "request_error"


def _format_validation_errors(errors: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    formatted: list[dict[str, str]] = []
    for error in errors:
        loc = [str(item) for item in error.get("loc", [])]
        location = loc[0] if loc else "body"
        field_parts = loc[1:] if len(loc) > 1 else []
        field = ".".join(field_parts) if field_parts else ""
        formatted.append(
            {
                "field": field,
                "location": location,
                "message": error.get("msg", "Invalid value"),
                "type": error.get("type", "validation_error"),
            }
        )
    return formatted


def _validation_message(errors: list[dict[str, str]]) -> str:
    return "Validation failed"


def _normalize_http_exception(http_exc: HTTPException) -> tuple[str, list[dict[str, Any]], str]:
    detail = http_exc.detail
    if isinstance(detail, str):
        return detail, [], _error_code_from_status(http_exc.status_code)
    if isinstance(detail, list):
        return "Validation failed", _format_validation_errors(detail), "validation_error"
    if isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("detail") or _status_phrase(http_exc.status_code))
        errors = detail.get("errors")
        if not isinstance(errors, list):
            errors = []
        error_code = str(detail.get("error_code") or _error_code_from_status(http_exc.status_code))
        return message, errors, error_code
    return _status_phrase(http_exc.status_code), [], _error_code_from_status(http_exc.status_code)


def _build_error_payload(message: str, *, error_code: str, errors: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "message": message,
        "data": None,
        "status": False,
        "detail": message,
        "error_code": error_code,
        "errors": errors or [],
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(request: Request, exc: AppException) -> JSONResponse:
        logger.warning("%s %s -> %s (%s)", request.method, request.url.path, exc.message, exc.code)
        return _json_response(exc.to_response(), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = _format_validation_errors(exc.errors())
        payload = _build_error_payload(_validation_message(errors), error_code="validation_error", errors=errors)
        logger.info("%s %s -> validation failed: %s", request.method, request.url.path, errors)
        return _json_response(payload, status_code=422)

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        message, errors, error_code = _normalize_http_exception(exc)
        logger.warning("%s %s -> HTTP %s: %s", request.method, request.url.path, exc.status_code, message)
        payload = _build_error_payload(message, error_code=error_code, errors=errors)
        return _json_response(payload, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        message = "Database constraint violation"
        error_code = "integrity_error"
        raw_message = str(getattr(exc, "orig", exc)).lower()

        if "unique" in raw_message or "duplicate" in raw_message:
            message = "A record with the same unique value already exists"
            error_code = "duplicate_resource"
        elif "foreign key" in raw_message:
            message = "The request references a related record that does not exist"
            error_code = "invalid_reference"

        logger.exception("%s %s -> integrity error", request.method, request.url.path)
        payload = _build_error_payload(message, error_code=error_code)
        return _json_response(payload, status_code=409)

    @app.exception_handler(SQLAlchemyError)
    async def handle_sqlalchemy_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("%s %s -> database error", request.method, request.url.path)
        payload = DatabaseException().to_response()
        return _json_response(payload, status_code=500)

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("%s %s -> unexpected server error", request.method, request.url.path)
        payload = InternalServerException("An unexpected server error occurred").to_response()
        return _json_response(payload, status_code=500)
