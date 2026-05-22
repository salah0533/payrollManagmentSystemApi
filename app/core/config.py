from __future__ import annotations

from dataclasses import dataclass, field

from app.utility.envvalues import get_env_value


def _get_env_str(key: str, default: str) -> str:
    value = get_env_value(key)
    return value if value not in (None, "") else default


def _get_env_int(key: str, default: int) -> int:
    value = get_env_value(key)
    return int(value) if value not in (None, "") else default


def _get_env_csv(key: str, default: list[str]) -> tuple[str, ...]:
    value = get_env_value(key)
    if value in (None, ""):
        return tuple(default)

    items = tuple(item.strip() for item in value.split(",") if item.strip())
    return items or tuple(default)


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: _get_env_str(
            "DATABASE_URL", "postgresql+psycopg://payrollpro:payrollpro@localhost:5432/payrollpro"
        )
    )
    jwt_secret_key: str = field(
        default_factory=lambda: _get_env_str("JWT_SECRET_KEY", "development-jwt-secret-change-me")
    )
    jwt_algorithm: str = field(default_factory=lambda: _get_env_str("JWT_ALGORITHM", "HS256"))
    access_token_expire_minutes: int = field(default_factory=lambda: _get_env_int("ACCESS_TOKEN_EXPIRE_MINUTES", 60))
    refresh_token_expire_minutes: int = field(
        default_factory=lambda: _get_env_int("REFRESH_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7)
    )
    default_admin_username: str = field(default_factory=lambda: _get_env_str("DEFAULT_ADMIN_USERNAME", "admin"))
    default_admin_email: str = field(default_factory=lambda: _get_env_str("DEFAULT_ADMIN_EMAIL", "admin@example.com"))
    default_admin_password: str = field(default_factory=lambda: _get_env_str("DEFAULT_ADMIN_PASSWORD", "admin"))
    api_host: str = field(default_factory=lambda: _get_env_str("API_HOST", "127.0.0.1"))
    api_port: int = field(default_factory=lambda: _get_env_int("API_PORT", 8000))
    api_workers: int = field(default_factory=lambda: _get_env_int("API_WORKERS", 1))
    cors_origins: tuple[str, ...] = field(default_factory=lambda: _get_env_csv("CORS_ORIGINS", ["*"]))


settings = Settings()
