"""¿Quién hace la petición, en qué organización y qué puede hacer? (F0-02)

Lo resuelve wise-comun, igual que en los demás servicios: valida el access token de
Cognito, lee la organización del encabezado X-Organization-Id y le pregunta a Identidad
(GET /autorizacion) quién es la persona, sus roles y sus asignaciones. Este servicio no
lee las tablas de Identidad.

Los endpoints exigen permisos, nunca roles: así cada organización cambia su matriz sin
tocar el código. En Identidad "ver" no es un permiso aparte: es tener el permiso con nivel
Consulta, por eso las lecturas piden `clientes.crear` con lectura=True.
"""

from typing import Annotated, Final
from uuid import UUID

from fastapi import Depends
from pydantic import BaseModel
from wise_comun.acceso import Decision
from wise_comun.autorizacion import exige
from wise_comun.deps import ContextoActual

from app.core.exceptions import BadRequestError, ForbiddenError

# ── Permisos que usa este servicio (los define el catálogo de Identidad) ──
CLIENTES_CREAR: Final = "clientes.crear"  # Crear clientes y compromisos, y asignar socio y gerente
CLIENTES_ESTADO_CAMBIAR: Final = "clientes.estado.cambiar"  # Activar o inactivar clientes


class Principal(BaseModel):
    """La persona que hace la petición. `id` es el de Identidad (no el sub de Cognito)."""

    id: UUID
    email: str | None = None
    full_name: str | None = None


def get_current_principal(ctx: ContextoActual) -> Principal:
    return Principal(id=ctx.user_id, email=ctx.email, full_name=ctx.full_name)


def get_organization_id(ctx: ContextoActual) -> UUID:
    """La organización activa (la firma). Sin ella no hay permisos: 400."""
    if ctx.organization_id is None:
        raise BadRequestError("The X-Organization-Id header is required")
    return ctx.organization_id


def require_whole_organization(decision: Decision) -> None:
    """Para lo que no es de una empresa existente (p. ej. crear un cliente nuevo): el
    permiso tiene que alcanzar a toda la organización, no solo a sus compromisos."""
    if not decision.toda_la_organizacion:
        raise ForbiddenError()


PrincipalDep = Annotated[Principal, Depends(get_current_principal)]
OrganizationDep = Annotated[UUID, Depends(get_organization_id)]
# Decisión de Identidad: si puede y sobre qué información (toda la organización, sus
# compromisos o sus empresas). 403 si no tiene el permiso en ninguna parte
CanCreateClientsDep = Annotated[Decision, Depends(exige(CLIENTES_CREAR))]
CanReadClientsDep = Annotated[Decision, Depends(exige(CLIENTES_CREAR, lectura=True))]
