import os

# Valores seguros ANTES de importar la app: los tests nunca usan la base de datos del .env real.
# docker-compose.test.yml / CI los reemplazan con variables de entorno reales.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5434/exogena_test"
)
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-000")

import pytest  # noqa: E402
from pytest_asyncio import is_async_test  # noqa: E402


def pytest_collection_modifyitems(items):
    # Un solo event loop para toda la ejecución (el fixture del engine de BD es de sesión)
    session_loop = pytest.mark.asyncio(loop_scope="session")
    for item in items:
        if is_async_test(item):
            item.add_marker(session_loop, append=False)
        if "integration" in item.path.parts:
            item.add_marker(pytest.mark.integration)
