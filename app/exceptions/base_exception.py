from __future__ import annotations

from http import HTTPStatus
from typing import Any


class AppException(Exception):
    status_code = 400
    code = "application_error"
    default_message = "Application error"

    def __init__(
        self,
        message: str | None = None,
        *,
        status_code: int | None = None,
        code: str | None = None,
        errors: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.status_code = status_code or self.status_code
        self.code = code or self.code
        self.errors = errors or []
        self.headers = headers or {}
        super().__init__(self.message)

    def to_response(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "data": None,
            "status": False,
            "detail": self.message,
            "error_code": self.code,
            "errors": self.errors,
        }


class BadRequestException(AppException):
    status_code = 400
    code = "bad_request"
    default_message = "Bad request"


class UnauthorizedException(AppException):
    status_code = 401
    code = "unauthorized"
    default_message = "Authentication required"


class ForbiddenException(AppException):
    status_code = 403
    code = "forbidden"
    default_message = "You do not have permission to perform this action"


class NotFoundException(AppException):
    status_code = 404
    code = "not_found"
    default_message = "Requested resource was not found"


class ConflictException(AppException):
    status_code = 409
    code = "conflict"
    default_message = "Request conflicts with the current state of the resource"


class ValidationException(AppException):
    status_code = 422
    code = "validation_error"
    default_message = "Validation failed"

    @classmethod
    def for_field(
        cls,
        *,
        field: str,
        message: str,
        location: str = "body",
        error_type: str = "value_error",
    ) -> "ValidationException":
        return cls(
            errors=[
                {
                    "field": field,
                    "location": location,
                    "message": message,
                    "type": error_type,
                }
            ]
        )


class DatabaseException(AppException):
    status_code = 500
    code = "database_error"
    default_message = "A database error occurred while processing the request"


class InternalServerException(AppException):
    status_code = 500
    code = "internal_server_error"
    default_message = HTTPStatus.INTERNAL_SERVER_ERROR.phrase


class ResourceNotFoundException(NotFoundException):
    def __init__(self, resource_name: str, identifier: Any | None = None, message: str | None = None) -> None:
        resolved_message = message or (
            f"{resource_name} with identifier '{identifier}' was not found"
            if identifier is not None
            else f"{resource_name} not found"
        )
        super().__init__(resolved_message, code=f"{resource_name.lower().replace(' ', '_')}_not_found")
