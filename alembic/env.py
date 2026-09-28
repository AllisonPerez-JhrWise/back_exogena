import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.config import settings
from app.shared.models import SQLModel, load_all_models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

load_all_models()
target_metadata = SQLModel.metadata

# La base de datos RDS se comparte con otros servicios: solo administramos nuestros schemas,
# si no, autogenerate propondría borrar las tablas de todos los demás.
OWNED_SCHEMAS = {t.schema for t in target_metadata.tables.values() if t.schema}


def include_name(name, type_, parent_names) -> bool:
    if type_ == "schema":
        return name in OWNED_SCHEMAS
    return True


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        version_table=settings.db_version_table,
        compare_type=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse: `alembic upgrade head --sql`."""
    _configure(
        url=settings.database_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(
        settings.database_url,
        poolclass=pool.NullPool,
        connect_args=settings.db_connect_args,
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
