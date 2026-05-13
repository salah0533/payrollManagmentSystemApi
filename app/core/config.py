from __future__ import annotations

from dataclasses import dataclass

from app.utility.envvalues import get_env_value


@dataclass(frozen=True)
class Settings:
    database_url: str = get_env_value("DATABASE_URL") or "sqlite:///./app.db"
    jwt_secret_key: str = get_env_value("JWT_SECRET_KEY") or "development-jwt-secret-change-me"
    jwt_algorithm: str = get_env_value("JWT_ALGORITHM") or "HS256"
    access_token_expire_minutes: int = int(get_env_value("ACCESS_TOKEN_EXPIRE_MINUTES") or 60)
    refresh_token_expire_minutes: int = int(get_env_value("REFRESH_TOKEN_EXPIRE_MINUTES") or 60 * 24 * 7)
    default_admin_username: str = get_env_value("DEFAULT_ADMIN_USERNAME") or "admin"
    default_admin_email: str = get_env_value("DEFAULT_ADMIN_EMAIL") or "admin@example.com"
    default_admin_password: str = get_env_value("DEFAULT_ADMIN_PASSWORD") or "admin"


settings = Settings()

