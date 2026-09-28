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
    # Con el que corre la app. En AWS es wiseerp_app: puede usar las funciones app_* de la
    # plataforma y la seguridad por filas (RLS) le aplica.
    database_url: str
    # Con el que corren las migraciones (dueño del schema exogena). Vacío = database_url
    migration_database_url: str | None = None
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
    # El login no es de este servicio: lo hace la plataforma con Cognito.
    # PROVISIONAL hasta tener los datos de Cognito: tokens HS256 firmados con este secreto.
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    # Encabezado con el tenant (organización) en el que trabaja el usuario
    tenant_header: str = "X-Tenant-Id"

    # ── Front-end (Next.js) ──────────────────────────────────────────────
    # Lista JSON: CORS_ORIGINS=["https://app.example.com"]
    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def alembic_database_url(self) -> str:
        return self.migration_database_url or self.database_url

    @property
    def db_connect_args(self) -> dict[str, Any]:
        return {"ssl": self.db_ssl_mode} if self.db_ssl_mode else {}

    @model_validator(mode="after")
    def _check_consistency(self) -> "Settings":
        for url in (self.database_url, self.migration_database_url):
            if url and not url.startswith("postgresql+asyncpg://"):
                raise ValueError("Database URLs must use the postgresql+asyncpg:// driver")
        if self.is_production and "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS cannot contain '*' in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
