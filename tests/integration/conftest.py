"""Tests de integración: PostgreSQL real (`make test` lo corre en Docker).

Cada test corre dentro de una transacción que se revierte al final, aunque los
services hagan commit() (con join_transaction_mode se vuelve un SAVEPOINT)."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.database import get_session
from app.main import app
from app.shared.models import SQLModel, load_all_models


@pytest.fixture(scope="session")
async def engine():
    load_all_models()
    engine = create_async_engine(
        settings.database_url,
        poolclass=pool.NullPool,
        connect_args=settings.db_connect_args,
    )
    schemas = {t.schema for t in SQLModel.metadata.tables.values() if t.schema}
    async with engine.begin() as conn:
        for schema in schemas:
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
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
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def register(client):
    """Crea un usuario y devuelve sus encabezados Authorization."""

    async def _register(email: str, password: str = "password-123") -> dict:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "first_name": "Test",
                "last_name": "Prueba",
            },
        )
        assert response.status_code == 201, response.text
        token = response.json()["data"]["access_token"]
        client.cookies.clear()
        return {"Authorization": f"Bearer {token}"}

    return _register
