"""Imprime, como INSERT de SQL, los catálogos de la plataforma que hay en la RDS:
roles del sistema, permisos, sus asignaciones y la política de privacidad vigente.

No copia datos de tenants ni de usuarios. Lo usa `make db-sync-cloud` para generar
docker/db-init/20_catalogos.sql; se conecta con la DATABASE_URL de .env.aws.
"""

import asyncio
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import settings

HEADER = """\
-- ════════════════════════════════════════════════════════════════════════
-- Catálogos de la plataforma copiados de la RDS: roles del sistema, permisos,
-- sus asignaciones y la política de privacidad vigente. Mismos UUID que en la nube.
-- No incluye datos de tenants ni de usuarios.
-- NO se edita a mano. Para actualizarlo: make db-sync-cloud (requiere .env.aws)
-- ════════════════════════════════════════════════════════════════════════
"""

SYSTEM_ROLES = "tenant_id IS NULL"


def literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if hasattr(value, "isoformat"):
        value = value.isoformat()
    return "'" + str(value).replace("'", "''") + "'"


async def insert(
    conn: AsyncConnection, table: str, columns: Sequence[str], where: str = "TRUE"
) -> str:
    query = f"SELECT {', '.join(columns)} FROM public.{table} WHERE {where} ORDER BY 1"
    rows = (await conn.execute(text(query))).all()
    if not rows:
        return f"-- {table}: sin filas\n"
    values = ",\n".join("    (" + ", ".join(literal(v) for v in row) + ")" for row in rows)
    return (
        f"-- {table}: {len(rows)} filas\n"
        f"INSERT INTO public.{table} ({', '.join(columns)}) VALUES\n{values};\n"
    )


async def main() -> None:
    engine = create_async_engine(settings.database_url, connect_args=settings.db_connect_args)
    async with engine.connect() as conn:
        parts = [
            HEADER,
            # Versión de las migraciones de los otros servicios, como está en la nube
            await insert(conn, "alembic_version", ["version_num"]),
            await insert(conn, "alembic_version_extraccion", ["version_num"]),
            await insert(conn, "permissions", ["code", "description"]),
            await insert(
                conn,
                "roles",
                ["id", "tenant_id", "code", "name", "created_at", "updated_at"],
                SYSTEM_ROLES,
            ),
            await insert(
                conn,
                "role_permissions",
                ["role_id", "permission_code"],
                f"role_id IN (SELECT id FROM public.roles WHERE {SYSTEM_ROLES})",
            ),
            await insert(
                conn,
                "politicas_privacidad",
                ["version", "resumen", "url", "vigente_desde", "vigente"],
            ),
            "SELECT setval('public.politicas_privacidad_version_seq', "
            "(SELECT max(version) FROM public.politicas_privacidad));\n",
        ]
    await engine.dispose()
    print("\n".join(parts))


if __name__ == "__main__":
    asyncio.run(main())
