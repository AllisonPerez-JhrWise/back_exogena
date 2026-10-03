import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.auth import Principal, get_current_principal
from app.main import app


@pytest.fixture
def principal() -> Principal:
    return Principal(id=uuid.uuid4(), email="tester@example.com")


@pytest.fixture
def client():
    """Cliente sin base de datos: reemplaza las dependencias de service que necesites."""
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def authenticated(principal):
    app.dependency_overrides[get_current_principal] = lambda: principal
    return principal
