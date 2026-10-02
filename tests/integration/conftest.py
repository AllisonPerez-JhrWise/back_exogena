"""Tests de integración: PostgreSQL real (`make test` lo corre en Docker).

La base de pruebas se crea con docker/db-init, así que tiene la plataforma igual que la
nube: roles de la base, tablas de public con seguridad por filas y catálogos de roles y
permisos. Aquí solo se crean las tablas de exogena.

Cada test corre dentro de una transacción que se revierte al final, aunque los services
hagan commit() (con join_transaction_mode se vuelve un SAVEPOINT). Los datos de prueba
se preparan como superusuario; cada petición a la API corre como wiseerp_app, el usuario
de la app en AWS, para que la seguridad por filas aplique como en producción.
"""

from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import pool, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.database import get_session
from app.core.security import create_access_token
from app.main import app
from app.modules.platform.models import MembershipStatus, Role, SystemRole, TenantKind
from app.shared.models import DB_SCHEMA, SQLModel, load_all_models

APP_ROLE = "wiseerp_app"


def exogena_tables():
    return [t for t in SQLModel.metadata.sorted_tables if t.schema == DB_SCHEMA]


@pytest.fixture(scope="session")
async def engine():
    load_all_models()
    engine = create_async_engine(
        settings.async_database_url,
        poolclass=pool.NullPool,
        connect_args=settings.db_connect_args,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all, tables=exogena_tables())
        await conn.run_sync(SQLModel.metadata.create_all, tables=exogena_tables())
        # Los mismos permisos que da la migración 0001
        await conn.execute(text(f'GRANT USAGE ON SCHEMA "{DB_SCHEMA}" TO {APP_ROLE}'))
        await conn.execute(
            text(
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "{DB_SCHEMA}" '
                f"TO {APP_ROLE}"
            )
        )
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all, tables=exogena_tables())
    await engine.dispose()


@pytest.fixture
async def db_session(engine):
    async with engine.connect() as conn:
        transaction = await conn.begin()
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest.fixture
async def client(db_session):
    async def override_get_session():
        # Igual que la app real: corre como wiseerp_app y, si la petición falla,
        # se revierte lo que no se confirmó
        await db_session.execute(text(f"SET ROLE {APP_ROLE}"))
        try:
            yield db_session
        except Exception:
            await db_session.rollback()
            raise
        finally:
            await db_session.execute(text("RESET ROLE"))

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ── Datos de la plataforma (se insertan como superusuario, sin seguridad por filas) ──


class Platform:
    """Crea personas, tenants y membresías en las tablas de public.

    Cada método confirma (commit = liberar el SAVEPOINT): así una petición que falla y
    revierte no se lleva los datos de prueba. Todo se revierte igual al final del test."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def user(self, email: str, full_name: str = "Persona Prueba") -> UUID:
        user_id = uuid4()
        await self.session.execute(
            text(
                "INSERT INTO public.users (id, email, full_name, is_active) "
                "VALUES (:id, :email, :full_name, true)"
            ),
            {"id": user_id, "email": email.lower(), "full_name": full_name},
        )
        await self.session.commit()
        return user_id

    async def tenant(self, slug: str, kind: TenantKind = TenantKind.INTERNAL) -> UUID:
        tenant_id = uuid4()
        await self.session.execute(
            text(
                "INSERT INTO public.tenants (id, slug, name, kind, status) "
                "VALUES (:id, :slug, :slug, :kind, 'active')"
            ),
            {"id": tenant_id, "slug": slug, "kind": kind},
        )
        await self.session.commit()
        return tenant_id

    async def member(
        self,
        user_id: UUID,
        tenant_id: UUID,
        role: SystemRole,
        status: MembershipStatus = MembershipStatus.ACTIVE,
    ) -> UUID:
        role_id = await self.session.scalar(
            select(Role.id).where(Role.code == role, Role.tenant_id.is_(None))
        )
        membership_id = uuid4()
        await self.session.execute(
            text(
                "INSERT INTO public.memberships (id, user_id, tenant_id, status) "
                "VALUES (:id, :user_id, :tenant_id, :status)"
            ),
            {"id": membership_id, "user_id": user_id, "tenant_id": tenant_id, "status": status},
        )
        await self.session.execute(
            text("INSERT INTO public.membership_roles (membership_id, role_id) VALUES (:m, :r)"),
            {"m": membership_id, "r": role_id},
        )
        await self.session.commit()
        return membership_id


def auth_headers(user_id: UUID, tenant_id: UUID | None = None) -> dict[str, str]:
    """Encabezados de una petición autenticada (token provisional, hasta tener Cognito)."""
    headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}
    if tenant_id:
        headers[settings.tenant_header] = str(tenant_id)
    return headers


@pytest.fixture
def platform(db_session) -> Platform:
    return Platform(db_session)


@pytest.fixture
async def firm(platform) -> UUID:
    """El tenant de la firma (kind=internal)."""
    return await platform.tenant("jhr-wise")


@pytest.fixture
def staff(platform, firm):
    """Crea una persona de la firma con ese rol y devuelve sus encabezados."""

    async def _staff(
        email: str,
        role: SystemRole = SystemRole.ASOCIADO,
        status: MembershipStatus = MembershipStatus.ACTIVE,
    ) -> dict[str, str]:
        user_id = await platform.user(email)
        await platform.member(user_id, firm, role, status)
        return auth_headers(user_id, firm)

    return _staff


@pytest.fixture
async def admin(staff) -> dict[str, str]:
    """Encabezados de un administrador de la firma (tiene clientes.crear)."""
    return await staff("admin@jhrwise.com", SystemRole.ADMINISTRADOR)
