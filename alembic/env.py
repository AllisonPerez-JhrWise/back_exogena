from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection

from alembic import context
from app.core.config import settings
from app.shared.models import DB_SCHEMA, SQLModel, load_all_models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

load_all_models()
target_metadata = SQLModel.metadata

# La base de datos RDS se comparte con otros servicios: solo administramos el schema exogena.
# Las tablas de la plataforma (public.users, public.tenants...) están en los modelos para
# poder consultarlas y apuntarles con FK, pero las maneja el servicio de plataforma.
# Sin este filtro, autogenerate propondría crearlas, cambiarlas o borrarlas.


def include_name(name, type_, parent_names) -> bool:
    if type_ == "schema":
        # None = el schema por defecto (public). Se lee para resolver las FK hacia la
        # plataforma; include_object descarta sus tablas.
        return name in (DB_SCHEMA, None)
    return True


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    table = obj if type_ == "table" else getattr(obj, "table", None)
    return table is None or table.schema == DB_SCHEMA


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        include_object=include_object,
        version_table=settings.db_version_table,
        compare_type=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse: `alembic upgrade head --sql`."""
    _configure(
        url=settings.admin_database_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Con el dueño del schema exogena (DB_ADMIN_USER; vacío = DB_USER)
    engine = create_engine(settings.admin_database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        do_run_migrations(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
