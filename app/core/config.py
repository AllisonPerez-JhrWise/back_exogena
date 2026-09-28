from enum import StrEnum
from functools import lru_cache
from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Única fuente de configuración. Cada valor viene de variables de entorno / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── App ──────────────────────────────────────────────────────────────
    app_name: str = "back_exogena"
    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    # ── Base de datos ─────────────────────────────────────────────────────────
    # Debe usar el driver async: postgresql+asyncpg://usuario:clave@host:5432/bd
    database_url: str
    # Por proceso. Conexiones totales = pool_size + max_overflow, por cada worker/tarea
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_recycle_seconds: int = 1800
    # Modo SSL de asyncpg: disable | prefer | require | verify-ca | verify-full
    db_ssl_mode: str | None = None
    db_echo: bool = False
    # Tabla de versiones de Alembic propia: la base de datos RDS se comparte con otros servicios
    db_version_table: str = "alembic_version_exogena"

    # ── Autenticación ─────────────────────────────────────────────────────────────
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    auth_cookie_name: str = "access_token"
    # True en todo entorno servido por HTTPS (AWS)
    cookie_secure: bool = False
    # p. ej. ".jhrwise.com" para compartir la cookie entre los subdominios app. y api.
    cookie_domain: str | None = None

    # ── Front-end (Next.js) ──────────────────────────────────────────────
    # Lista JSON: CORS_ORIGINS=["https://app.example.com"]
    cors_origins: list[str] = ["http://localhost:3000"]
    # A dónde redirige el callback de Google después del login. Vacío = devuelve JSON
    frontend_url: str | None = None

    # ── Google OAuth (opcional) ──────────────────────────────────────────
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def google_enabled(self) -> bool:
        return all((self.google_client_id, self.google_client_secret, self.google_redirect_uri))

    @property
    def db_connect_args(self) -> dict[str, Any]:
        return {"ssl": self.db_ssl_mode} if self.db_ssl_mode else {}

    @model_validator(mode="after")
    def _check_consistency(self) -> "Settings":
        if not self.database_url.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg:// driver")
        if self.is_production:
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
            if "*" in self.cors_origins:
                raise ValueError("CORS_ORIGINS cannot contain '*' in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
