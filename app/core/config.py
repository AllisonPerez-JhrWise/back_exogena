from enum import StrEnum
from functools import lru_cache
from uuid import UUID

from pydantic import model_validator
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

    # ── Autenticación (la valida wise-comun: token de Cognito + Identidad) ───────────
    # SOLO DESARROLLO LOCAL, para usar la API sin usuario de la plataforma: sin token ni
    # Identidad, se actúa como dev_user_id, Administrador de la organización del encabezado
    # X-Organization-Id (o de dev_organization_id si no llega). Prohibido en producción.
    auth_bypass: bool = False
    dev_user_id: UUID = UUID(int=0)
    # La firma de `make seed`
    dev_organization_id: UUID | None = None

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

    def _url(self, usuario: str, clave: str) -> str:
        """Reemplaza el de AjustesBase, que pega la contraseña tal cual en el texto: una
        contraseña con @, /, # o : rompería la dirección. URL.create la escapa. Como
        database_url y admin_database_url (y wise_comun.db) la usan, todos quedan bien."""
        return URL.create(
            "postgresql+psycopg",
            username=usuario,
            password=clave,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"sslmode": self.db_sslmode},
        ).render_as_string(hide_password=False)

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
