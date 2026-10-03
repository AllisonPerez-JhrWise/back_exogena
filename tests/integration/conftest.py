"""Tests de integración: PostgreSQL real (`make test` lo corre en Docker).

La base de pruebas se crea con docker/db-init, así que tiene la plataforma igual que la
nube: roles de la base, tablas de public con seguridad por filas y catálogos de roles y
permisos. Aquí solo se crean las tablas de exogena.

Cada test corre dentro de una transacción que se revierte al final, aunque los services
hagan commit() (con join_transaction_mode se vuelve un SAVEPOINT). Los datos de prueba
se preparan como superusuario; cada petición a la API corre como wiseerp_app, el usuario
de la app en AWS.

Identidad no existe aquí: el doble de tests/integration/identity.py responde lo que
respondería GET /autorizacion, y wise-comun lo interpreta como en producción.
"""

from typing import Annotated
from uuid import UUID

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, pool, text
from sqlalchemy.orm import Session
from wise_comun import db as wise_db
from wise_comun import deps
from wise_comun.deps import CABECERA_ORGANIZACION

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.main import app
from app.shared.models import DB_SCHEMA, SQLModel, load_all_models
from tests.integration.identity import (
    FakeIdentity,
    MembershipStatus,
    SystemRole,
    token_for,
)

APP_ROLE = "wiseerp_app"


def exogena_tables():
    return [t for t in SQLModel.metadata.sorted_tables if t.schema == DB_SCHEMA]


@pytest.fixture(scope="session")
def engine():
    load_all_models()
    engine = create_engine(
        settings.database_url,
        poolclass=pool.NullPool,
    )
    with engine.begin() as conn:
        SQLModel.metadata.drop_all(conn, tables=exogena_tables())
        SQLModel.metadata.create_all(conn, tables=exogena_tables())
        # Los mismos permisos que da la migración 0001
        conn.execute(text(f'GRANT USAGE ON SCHEMA "{DB_SCHEMA}" TO {APP_ROLE}'))
        conn.execute(
            text(
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "{DB_SCHEMA}" '
                f"TO {APP_ROLE}"
            )
        )
    yield engine
    with engine.begin() as conn:
        SQLModel.metadata.drop_all(conn, tables=exogena_tables())
    engine.dispose()


@pytest.fixture
def db_session(engine):
    with engine.connect() as conn:
        transaction = conn.begin()
        session = Session(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def platform() -> FakeIdentity:
    """Identidad en memoria: personas, organizaciones y membresías de la prueba."""
    return FakeIdentity()


@pytest.fixture
def client(db_session, platform, monkeypatch):
    def override_get_db():
        # Igual que la app real: corre como wiseerp_app y, si la petición falla,
        # se revierte lo que no se confirmó
        db_session.execute(text(f"SET ROLE {APP_ROLE}"))
        try:
            yield db_session
        except Exception:
            db_session.rollback()
            raise
        finally:
            db_session.execute(text("RESET ROLE"))

    def claims(token: Annotated[str, Depends(deps.token_actual)]) -> dict:
        """En vez de validar el token contra Cognito: solo los del doble son válidos."""
        if not platform.knows(token):
            raise UnauthorizedError("Invalid token")
        return {"sub": token}

    # Sin caché: cada petición vuelve a preguntar (en una prueba el alcance cambia)
    monkeypatch.setattr(deps, "_VIGENCIA_CACHE", 0)
    deps.registrar_resolutor(platform.resolve)
    app.dependency_overrides[wise_db.get_db] = override_get_db
    app.dependency_overrides[deps.current_claims] = claims
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    deps.registrar_resolutor(deps._por_http)


def auth_headers(user_id: UUID, organization_id: UUID | None = None) -> dict[str, str]:
    """Encabezados de una petición autenticada: token y organización (X-Organization-Id)."""
    headers = {"Authorization": f"Bearer {token_for(user_id)}"}
    if organization_id:
        headers[CABECERA_ORGANIZACION] = str(organization_id)
    return headers


@pytest.fixture
def firm(platform) -> UUID:
    """La organización de la firma."""
    return platform.tenant("jhr-wise")


@pytest.fixture
def staff(platform, firm):
    """Crea una persona de la firma con ese rol y devuelve sus encabezados."""

    def _staff(
        email: str,
        role: SystemRole = SystemRole.ASOCIADO,
        status: MembershipStatus = MembershipStatus.ACTIVE,
    ) -> dict[str, str]:
        user_id = platform.user(email)
        platform.member(user_id, firm, role, status)
        return auth_headers(user_id, firm)

    return _staff


@pytest.fixture
def admin(staff) -> dict[str, str]:
    """Encabezados de un administrador de la firma (tiene clientes.crear)."""
    return staff("admin@jhrwise.com", SystemRole.ADMINISTRADOR)
