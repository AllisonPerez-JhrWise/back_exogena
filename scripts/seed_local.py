"""SOLO LOCAL: deja la base local lista para probar la API.

Crea (si no existen) la organización de la firma, un administrador de prueba con su
membresía y el catálogo inicial, e imprime los encabezados para usar en /docs.
En AWS la firma y las personas las crea la plataforma, nunca este script.

Uso: make seed
"""

import asyncio
import os
import sys
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Environment, settings
from app.core.security import create_access_token
from app.modules.catalog.seed import seed_catalog

FIRM_SLUG = "jhr-wise"
FIRM_NAME = "JHR Wise"
# ID fijo: es el DEV_TENANT_ID de .env_example (AUTH_BYPASS sin X-Tenant-Id usa esta firma)
FIRM_ID = UUID("00000000-0000-4000-8000-00000000f1a0")
# (correo, nombre, rol en la firma): administrador y el equipo para crear compromisos
PEOPLE = [
    ("admin@jhrwise.com", "Administrador Local", "administrador"),
    ("juan.restrepo@jhrwise.com", "Juan Restrepo", "socio"),
    ("maria.gomez@jhrwise.com", "María Gómez", "gerente"),
]


def superuser_url() -> str:
    """Las tablas de la plataforma tienen seguridad por filas: se escriben como superusuario."""
    user, password = os.environ["POSTGRES_USER"], os.environ["POSTGRES_PASSWORD"]
    return f"postgresql+asyncpg://{user}:{password}@db:5432/{os.environ['POSTGRES_DB']}"


async def get_or_create(
    session: AsyncSession, find: str, insert: str, params: dict, new_id: UUID | None = None
) -> UUID:
    found = await session.scalar(text(find), params)
    if found:
        return found
    new_id = new_id or uuid4()
    await session.execute(text(insert), {**params, "id": new_id})
    return new_id


async def add_person(session: AsyncSession, firm_id: UUID, email: str, name: str, role: str):
    """Persona con membresía activa en la firma y ese rol del sistema."""
    user_id = await get_or_create(
        session,
        "SELECT id FROM public.users WHERE email = :email",
        "INSERT INTO public.users (id, email, full_name, is_active) "
        "VALUES (:id, :email, :name, true)",
        {"email": email, "name": name},
    )
    membership_id = await get_or_create(
        session,
        "SELECT id FROM public.memberships WHERE user_id = :user_id AND tenant_id = :tenant_id",
        "INSERT INTO public.memberships (id, user_id, tenant_id, status) "
        "VALUES (:id, :user_id, :tenant_id, 'active')",
        {"user_id": user_id, "tenant_id": firm_id},
    )
    await session.execute(
        text(
            "INSERT INTO public.membership_roles (membership_id, role_id) "
            "SELECT :membership_id, id FROM public.roles "
            "WHERE code = :role AND tenant_id IS NULL "
            "ON CONFLICT DO NOTHING"
        ),
        {"membership_id": membership_id, "role": role},
    )
    return user_id


async def main() -> int:
    if settings.environment != Environment.LOCAL:
        print("ERROR: este script solo corre con ENVIRONMENT=local")
        return 1

    engine = create_async_engine(superuser_url())
    async with AsyncSession(engine, expire_on_commit=False) as session:
        firm_id = await get_or_create(
            session,
            "SELECT id FROM public.tenants WHERE slug = :slug",
            "INSERT INTO public.tenants (id, slug, name, kind, status) "
            "VALUES (:id, :slug, :name, 'internal', 'active')",
            {"slug": FIRM_SLUG, "name": FIRM_NAME},
            new_id=FIRM_ID,
        )
        people = [await add_person(session, firm_id, *person) for person in PEOPLE]
        admin_id = people[0]
        result = await seed_catalog(session, firm_id, admin_id)
        await session.commit()
    await engine.dispose()

    token = create_access_token(admin_id, expires_delta=timedelta(hours=12))
    names = ", ".join(f"{name} ({role})" for _, name, role in PEOPLE)
    print(
        f"OK - Firma '{FIRM_NAME}' lista con: {names}.\n"
        f"Catálogo: {result.obligations} obligaciones, {result.service_types} tipos de servicio"
        f" y {result.services} servicios nuevos.\n\n"
        f"En .env debe estar: DEV_TENANT_ID={firm_id}\n"
        "Con AUTH_BYPASS=true la API funciona sin token ni X-Tenant-Id.\n\n"
        "Para probar como el administrador en http://localhost:8000/docs (12 horas):\n"
        f"  1. Boton 'Authorize', pega este token:\n     {token}\n"
        f"  2. En cada endpoint, campo {settings.tenant_header}:\n     {firm_id}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
