import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError
from app.shared.responses import ErrorResponse

logger = logging.getLogger(__name__)


def error_response(status_code: int, message: str, code: str, details=None, headers=None):
    body = ErrorResponse(message=message, code=code, details=details)
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body), headers=headers)


async def app_error_handler(request: Request, exc: AppError):
    return error_response(exc.status_code, exc.message, exc.code, exc.details)


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return error_response(exc.status_code, str(exc.detail), "http_error", headers=exc.headers)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = [
        {"loc": ".".join(map(str, err["loc"])), "msg": err["msg"], "type": err["type"]}
        for err in exc.errors()
    ]
    return error_response(422, "Validation error", "validation_error", details)


async def integrity_error_handler(request: Request, exc: IntegrityError):
    logger.warning("Integrity error: %s", exc.orig)
    return error_response(
        status.HTTP_409_CONFLICT,
        "The data conflicts with existing records (duplicate or invalid reference).",
        "integrity_error",
    )


async def data_error_handler(request: Request, exc: DataError):
    logger.warning("Data error: %s", exc.orig)
    return error_response(
        status.HTTP_400_BAD_REQUEST, "Invalid data for the database.", "data_error"
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error", "internal_error"
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(DataError, data_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
