import logging

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.database import SessionDep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Liveness: the process is up")
def health():
    return {"status": "ok"}


@router.get("/health/ready", summary="Readiness: the database answers")
def ready(session: SessionDep):
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:
        # Una sola línea, sin traceback: el ALB consulta esto cada pocos segundos
        logger.warning("Readiness check failed: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unavailable"},
        )
    return {"status": "ok"}
