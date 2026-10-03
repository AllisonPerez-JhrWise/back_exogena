from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health, v1
from app.core.config import Environment, settings
from app.core.database import engine
from app.core.handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestContextMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    engine.dispose()


def create_app() -> FastAPI:
    setup_logging(settings.log_level, json_logs=settings.environment != Environment.LOCAL)

    # La documentación no se expone en producción
    docs = not settings.is_production
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", settings.tenant_header],
        expose_headers=["X-Request-ID"],
    )
    # Se agrega de último = es la capa más externa:
    # toda petición (incluso las rechazadas por CORS) recibe un id
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(v1.router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
