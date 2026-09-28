"""¿Quién está haciendo la petición?

Solo valida el JWT, no consulta la base de datos. Así cada módulo es independiente
de dónde vivan los usuarios (este servicio, otro microservicio o un proveedor de
identidad). Los módulos que necesiten el registro completo del usuario usan su
propia dependencia (ver `app.modules.accounts.dependencies.get_active_user`).
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


class Principal(BaseModel):
    id: UUID
    email: str | None = None


async def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    """Toma el token de `Authorization: Bearer` (BFF / servicios)
    o de la cookie HttpOnly (navegador)."""
    token = (
        credentials.credentials if credentials else request.cookies.get(settings.auth_cookie_name)
    )
    if not token:
        raise UnauthorizedError()

    claims = decode_access_token(token)
    try:
        return Principal(id=claims["sub"], email=claims.get("email"))
    except ValidationError:
        raise UnauthorizedError("Invalid token") from None


PrincipalDep = Annotated[Principal, Depends(get_current_principal)]
