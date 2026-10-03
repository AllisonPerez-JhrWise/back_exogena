# De dónde sale wise-comun: "index" (CodeArtifact, para AWS) o "local" (la carpeta
# ../wise-comun, que docker-compose.yml pasa como contexto adicional). Va antes del primer
# FROM porque se usa para elegir una etapa.
ARG WISE_COMUN_FROM=index

# ── Build: instala las dependencias en un virtualenv aislado ─────────────────
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements/ /tmp/requirements/
RUN pip install -r /tmp/requirements/base.txt

# ── wise-comun desde CodeArtifact (AWS) ─────────────────────────────────────
# El índice lleva el token dentro: entra como secreto y no como argumento, para que no
# quede escrito en la imagen. Se construye con:
#   docker build --secret id=indice,env=INDICE .   (INDICE = wise-erp-infra/ops/codeartifact.sh url)
FROM builder AS wise-comun-index
RUN --mount=type=secret,id=indice \
    PIP_EXTRA_INDEX_URL="$(cat /run/secrets/indice)" pip install -r /tmp/requirements/wise-comun.txt

# ── wise-comun desde la carpeta del Escritorio (solo desarrollo local) ───────────
FROM builder AS wise-comun-local
COPY --from=wise_comun . /tmp/wise-comun
RUN pip install /tmp/wise-comun

FROM wise-comun-${WISE_COMUN_FROM} AS deps

# ── Runtime: imagen liviana, usuario sin privilegios (no root) ────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    WEB_CONCURRENCY=2

RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY --from=deps /opt/venv /opt/venv
COPY --chown=app:app app ./app
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini ./

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

# Detrás de un ALB de AWS: confía en los encabezados X-Forwarded-*. Las migraciones corren como un paso aparte.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY} --proxy-headers --forwarded-allow-ips='*' --no-access-log"]
