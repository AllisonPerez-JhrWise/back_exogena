"""Modo de desarrollo local (AUTH_BYPASS=true): usar la API sin token ni Identidad.

Sirve mientras no se tiene usuario de la plataforma o no se quiere levantar wise-auth.
Sin token, se actúa como `dev_user_id`, Administrador de la organización que llega en
X-Organization-Id (o de `dev_organization_id`). Lo demás funciona igual: los permisos se
siguen exigiendo con `exige`, solo que la respuesta de Identidad la da este módulo.

Prohibido fuera de local: Settings no arranca con AUTH_BYPASS en producción.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import FastAPI, Header
from sqlalchemy.orm import Session
from wise_comun import deps

from app.core.auth import CLIENTES_CREAR, CLIENTES_ESTADO_CAMBIAR
from app.core.config import settings

DEV_TOKEN = "dev"


def _organization(
    x_organization_id: Annotated[str | None, Header()] = None,
) -> UUID | None:
    return deps.organizacion_declarada(x_organization_id) or settings.dev_organization_id


def _identity(token: str, claims: dict, organization: UUID | None, db: Session) -> dict[str, Any]:
    """Lo que respondería Identidad (GET /autorizacion) para un Administrador."""
    administrador = {
        "ambito": "general",
        "tipo": "interno",
        "permisos": {CLIENTES_CREAR: "si", CLIENTES_ESTADO_CAMBIAR: "si"},
    }
    return {
        "usuario": {
            "id": str(settings.dev_user_id),
            "email": "dev@localhost",
            "nombre": "Desarrollo local",
        },
        "organizacion": (
            {"id": str(organization), "tipo": "firma"} if organization is not None else None
        ),
        "roles": {"administrador": administrador},
        "generales": ["administrador"],
        "compromisos": {},
        "empresas": [],
        "consentimiento_pendiente": None,
    }


def enable_dev_access(app: FastAPI) -> None:
    deps.registrar_resolutor(_identity)
    app.dependency_overrides[deps.token_actual] = lambda: DEV_TOKEN
    app.dependency_overrides[deps.current_claims] = lambda: {"sub": DEV_TOKEN}
    app.dependency_overrides[deps.organizacion_declarada] = _organization
