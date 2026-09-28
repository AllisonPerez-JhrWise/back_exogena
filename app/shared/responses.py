from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Formato de toda respuesta exitosa: {ok, message, data}."""

    ok: bool = True
    message: str = "OK"
    data: T | None = None


class ErrorResponse(BaseModel):
    """Formato de todo error: el front revisa `ok` y usa `code` para su lógica."""

    ok: bool = False
    message: str
    code: str
    details: Any = None
