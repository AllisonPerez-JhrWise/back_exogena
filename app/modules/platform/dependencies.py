from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header

from app.core.auth import Principal, PrincipalDep
from app.core.config import settings
from app.core.database import SessionDep, set_db_context
from app.core.exceptions import BadRequestError, ForbiddenError
from app.modules.platform.models import Permission
from app.modules.platform.repository import PlatformRepository


async def get_tenant_id(
    tenant_id: Annotated[UUID | None, Header(alias=settings.tenant_header)] = None,
) -> UUID:
    """Tenant (organización) en el que trabaja el usuario, enviado por el front."""
    if tenant_id is None:
        raise BadRequestError(f"The {settings.tenant_header} header is required")
    return tenant_id


def require_permission(code: Permission):
    """Deja pasar solo a quien tenga ese permiso en el tenant del encabezado (si no, 403).
    También declara el contexto de la seguridad por filas para el resto de la petición."""

    async def dependency(
        principal: PrincipalDep,
        session: SessionDep,
        tenant_id: Annotated[UUID, Depends(get_tenant_id)],
    ) -> Principal:
        await set_db_context(session, user_id=principal.id, tenant_id=tenant_id)
        if not await PlatformRepository(session).has_permission(principal.id, tenant_id, code):
            raise ForbiddenError()
        return principal

    return dependency


TenantDep = Annotated[UUID, Depends(get_tenant_id)]
# Quien hace la petición, garantizando que tiene ese permiso en su tenant
CanCreateClientsDep = Annotated[Principal, Depends(require_permission(Permission.CLIENTES_CREAR))]
CanReadClientsDep = Annotated[Principal, Depends(require_permission(Permission.CLIENTES_LEER))]
