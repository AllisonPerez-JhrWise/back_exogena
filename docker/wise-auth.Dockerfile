# SOLO DESARROLLO LOCAL: wise-auth (Identidad) para que exógena le pregunte quién llama y
# qué puede hacer, como en producción. Lo usan `make auth-up` / `make auth-down`.
#
# El contexto es la carpeta ../wise-auth y wise-comun llega como contexto adicional desde
# ../wise-comun (sin CodeArtifact). Se copia solo lo que hace falta para instalarlo: así no
# entra el .venv de Windows ni el .env con las credenciales (las recibe al arrancar).
FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONUNBUFFERED=1

COPY --from=wise_comun pyproject.toml /tmp/wise-comun/pyproject.toml
COPY --from=wise_comun src /tmp/wise-comun/src
RUN pip install -q /tmp/wise-comun

COPY pyproject.toml /tmp/wise-auth/pyproject.toml
COPY src /tmp/wise-auth/src
RUN pip install -q /tmp/wise-auth

EXPOSE 8002
CMD ["uvicorn", "wise_auth.main:app", "--host", "0.0.0.0", "--port", "8002"]
