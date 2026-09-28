import importlib
import pkgutil
import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import DateTime, Field, SQLModel
from sqlmodel.main import SQLModelMetaclass

# Nombres de restricciones predecibles para que las migraciones de Alembic sean reproducibles
SQLModel.metadata.naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

MODULES_PACKAGE = "app.modules"


def utc_now() -> datetime:
    return datetime.now(UTC)


class AutoTableMeta(SQLModelMetaclass):
    """Toda subclase de BaseTable es una tabla, guardada en el schema de PostgreSQL
    con el nombre de su módulo: app/modules/<modulo>/models.py -> schema <modulo>.
    Se puede cambiar con `__table_args__ = {"schema": "..."}`."""

    def __new__(cls, name, bases, dct, **kwargs):
        is_table = any(isinstance(base, AutoTableMeta) for base in bases)
        if is_table:
            kwargs.setdefault("table", True)

            parts = dct.get("__module__", "").split(".")
            if dct.get("__module__", "").startswith(MODULES_PACKAGE + ".") and len(parts) > 3:
                table_args = dct.get("__table_args__") or {}
                if isinstance(table_args, dict):
                    table_args.setdefault("schema", parts[2])
                    dct["__table_args__"] = table_args

        return super().__new__(cls, name, bases, dct, **kwargs)


class BaseTable(SQLModel, metaclass=AutoTableMeta):
    # NOTA: nunca usar `sa_column=Column(...)` aquí. El mismo objeto Column quedaría
    # compartido por todas las tablas hijas y SQLAlchemy lanza "already assigned to Table".
    # Usar `sa_type` / `sa_column_kwargs` para que cada tabla tenga su propia Column.
    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    is_deleted: bool = Field(default=False, description="Soft delete flag")
    is_active: bool = Field(default=True, description="Whether the row is available")

    created_at: datetime = Field(
        default_factory=utc_now, sa_type=DateTime(timezone=True), nullable=False
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"onupdate": utc_now},
        nullable=True,
    )

    # UUID simples (sin FK): el usuario puede vivir en otro servicio / proveedor de identidad
    created_by: UUID | None = Field(default=None, nullable=True)
    updated_by: UUID | None = Field(default=None, nullable=True)


def load_all_models() -> None:
    """Importa cada app/modules/*/models.py para que SQLModel.metadata conozca todas
    las tablas (lo usan Alembic y los tests). Los módulos nuevos se detectan solos."""
    package = importlib.import_module(MODULES_PACKAGE)
    for module in pkgutil.iter_modules(package.__path__):
        if module.ispkg:
            try:
                importlib.import_module(f"{MODULES_PACKAGE}.{module.name}.models")
            except ModuleNotFoundError as exc:
                if exc.name != f"{MODULES_PACKAGE}.{module.name}.models":
                    raise
