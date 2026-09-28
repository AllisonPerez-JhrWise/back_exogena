import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.auth import Principal, get_current_principal
from app.main import app


@pytest.fixture
def principal() -> Principal:
    return Principal(id=uuid.uuid4(), email="tester@example.com")


@pytest.fixture
async def client():
    """Cliente sin base de datos: reemplaza las dependencias de service que necesites."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def authenticated(principal):
    app.dependency_overrides[get_current_principal] = lambda: principal
    return principal
