"""Tokens PROVISIONALES (HS256) mientras se integra Cognito.

El login lo hace la plataforma con Cognito; este servicio solo valida el token. Cuando
lleguen los datos de Cognito (región, User Pool, App Client), `decode_access_token`
validará con las llaves públicas del pool (RS256) y `sub` será el cognito_sub.
`create_access_token` existe solo para pruebas y desarrollo local.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedError


def create_access_token(
    subject: Any,
    claims: dict[str, Any] | None = None,
    expires_delta: timedelta = timedelta(hours=1),
) -> str:
    now = datetime.now(UTC)
    payload = {**(claims or {}), "sub": str(subject), "iat": now, "exp": now + expires_delta}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp"]},
        )
    except jwt.PyJWTError:
        raise UnauthorizedError("Invalid or expired token") from None
    return payload
