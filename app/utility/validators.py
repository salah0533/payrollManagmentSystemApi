from __future__ import annotations

from datetime import datetime

from app.exceptions.base_exception import ValidationException


def validate_year_month(value: str, *, field: str = "month", location: str = "path") -> str:
    try:
        datetime.strptime(value, "%Y-%m")
    except ValueError as exc:
        raise ValidationException.for_field(
            field=field,
            message="Invalid format. Use YYYY-MM",
            location=location,
            error_type="value_error.datetime",
        ) from exc
    return value
