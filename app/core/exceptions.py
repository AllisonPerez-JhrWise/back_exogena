"""Excepciones de dominio (errores de negocio).

Los services y repositories lanzan estas, nunca fastapi.HTTPException, para que la
lógica de negocio no dependa de HTTP. `app.core.handlers` las traduce a respuestas.
"""

from typing import Any


class AppError(Exception):
    status_code: int = 400
    code: str = "bad_request"
    message: str = "Bad request"

    def __init__(self, message: str | None = None, *, details: Any = None):
        self.message = message or self.message
        self.details = details
        super().__init__(self.message)


class BadRequestError(AppError):
    pass


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Not authenticated"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    message = "You do not have permission to perform this action"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "Resource not found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "Resource already exists"


class BusinessRuleError(AppError):
    status_code = 422
    code = "business_rule"
    message = "Business rule violated"
