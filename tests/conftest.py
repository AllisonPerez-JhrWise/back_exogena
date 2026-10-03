import os

# Valores seguros ANTES de importar la app: los tests nunca usan la base de datos del .env real.
# docker-compose.test.yml / CI los reemplazan con variables de entorno reales.
os.environ.setdefault("ENVIRONMENT", "test")
for name, value in {
    "DB_HOST": "localhost",
    "DB_PORT": "5434",
    "DB_NAME": "exogena_test",
    "DB_USER": "postgres",
    "DB_PASSWORD": "postgres",
    "DB_SSLMODE": "disable",
    "COGNITO_USER_POOL_ID": "us-east-2_test",
    "COGNITO_CLIENT_ID": "test-client",
}.items():
    os.environ.setdefault(name, value)
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-000")
# Siempre apagado (aunque el .env local lo tenga encendido): los tests que lo usan lo activan
os.environ["AUTH_BYPASS"] = "false"

import pytest  # noqa: E402


def pytest_collection_modifyitems(items):
    for item in items:
        if "integration" in item.path.parts:
            item.add_marker(pytest.mark.integration)
