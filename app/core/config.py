from enum import StrEnum
from functools import lru_cache
from typing import Any
from uuid import UUID

from pydantic import Field, model_validator
from sqlalchemy.engine import URL
from wise_comun.config import AjustesBase, registrar


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(AjustesBase):
    """Única fuente de configuración. Cada valor viene de variables de entorno / .env.

    Lo común a todos los servicios —base de datos por partes (DB_HOST, DB_USER…), Cognito,
    dirección de Identidad— viene de `AjustesBase` de wise-comun, como en wise-auth. Aquí
    queda solo lo de exógena."""

    # ── App ──────────────────────────────────────────────────────────────
    app_name: str = "back_exogena"
    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    # ── Base de datos ─────────────────────────────────────────────────────────
    # Schema propio del servicio (wise-comun lo pone como search_path)
    db_schema: str = "exogena"
    # Por proceso. Conexiones totales = pool_size + max_overflow, por cada worker/tarea
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_recycle_seconds: int = 1800
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
    # SOLO PARA PRUEBAS mientras llegan Cognito y el tenant: sin token se actúa como
    # dev_user_id, sin X-Tenant-Id se ve todo y no se revisan permisos. Prohibido en producción.
    auth_bypass: bool = False
    dev_user_id: UUID = UUID(int=0)
    # Con AUTH_BYPASS, tenant que se usa si no llega X-Tenant-Id (la firma de `make seed`).
    # Vacío = sin tenant: se ve todo, pero lo que necesita una organización responde 400.
    dev_tenant_id: UUID | None = None

    # ── Reglas del RUT (parámetros de la tarea; F0-09 aún no existe en la plataforma) ──
    # rut.dias_generacion_maxima: antigüedad máxima del PDF al cargar el RUT actual
    rut_max_generation_days: int = 30
    # rut.meses_vigencia_compromiso: después de esto la empresa queda "RUT por renovar"
    rut_renewal_months: int = 12

    # ── Front-end (Next.js) ──────────────────────────────────────────────
    # Lista JSON: CORS_ORIGINS=["https://app.example.com"]
    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    # ── Conexión async (PROVISIONAL: hasta pasar el servicio a síncrono con wise_comun.db) ──
    # Se arma con URL.create y no con texto: así una contraseña con caracteres especiales
    # (@, /, :…) no rompe la dirección.

    def _async_url(self, user: str, password: str) -> str:
        return URL.create(
            "postgresql+asyncpg",
            username=user,
            password=password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        ).render_as_string(hide_password=False)

    @property
    def async_database_url(self) -> str:
        """La app: DB_USER (en AWS, el rol de aplicación, sujeto a RLS)."""
        return self._async_url(self.db_user, self.db_password)

    @property
    def alembic_database_url(self) -> str:
        """Las migraciones: DB_ADMIN_USER, el dueño del schema exogena (vacío = DB_USER)."""
        if self.db_admin_user and self.db_admin_password:
            return self._async_url(self.db_admin_user, self.db_admin_password)
        return self.async_database_url

    @property
    def db_connect_args(self) -> dict[str, Any]:
        # asyncpg recibe el modo SSL como argumento (disable | prefer | require…)
        return {"ssl": self.db_sslmode}

    @model_validator(mode="after")
    def _check_consistency(self) -> "Settings":
        if self.is_production and "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS cannot contain '*' in production")
        if self.is_production and self.auth_bypass:
            raise ValueError("AUTH_BYPASS cannot be enabled in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


# wise-comun lee los ajustes de aquí (lo mismo que hace wise-auth en su config.py)
registrar(get_settings)

settings = get_settings()
