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
) -> UUID | None:
    """Tenant (organización) en el que trabaja el usuario, enviado por el front.
    Solo con AUTH_BYPASS (pruebas locales) puede faltar: se usa DEV_TENANT_ID, o ninguno
    (entonces se ve todo)."""
    if tenant_id is not None:
        return tenant_id
    if settings.auth_bypass:
        return settings.dev_tenant_id
    raise BadRequestError(f"The {settings.tenant_header} header is required")


async def require_tenant_id(tenant_id: Annotated[UUID | None, Depends(get_tenant_id)]) -> UUID:
    """Para lo que siempre necesita una organización (p. ej. listar sus personas)."""
    if tenant_id is None:
        raise BadRequestError(
            f"The {settings.tenant_header} header is required (or DEV_TENANT_ID in local tests)"
        )
    return tenant_id


def require_permission(code: Permission):
    """Deja pasar solo a quien tenga ese permiso en el tenant del encabezado (si no, 403).
    También declara el contexto de la seguridad por filas para el resto de la petición.
    Con AUTH_BYPASS y sin tenant no se revisa el permiso (solo pruebas locales)."""

    async def dependency(
        principal: PrincipalDep,
        session: SessionDep,
        tenant_id: Annotated[UUID | None, Depends(get_tenant_id)],
    ) -> Principal:
        await set_db_context(session, user_id=principal.id, tenant_id=tenant_id)
        # Solo con AUTH_BYPASS: sin tenant, o sin token (usuario de pruebas), no se revisa
        if tenant_id is None or (settings.auth_bypass and principal.id == settings.dev_user_id):
            return principal
        if not await PlatformRepository(session).has_permission(principal.id, tenant_id, code):
            raise ForbiddenError()
        return principal

    return dependency


# Tenant del encabezado; None solo con AUTH_BYPASS (entonces no se filtra por organización)
TenantDep = Annotated[UUID | None, Depends(get_tenant_id)]
RequiredTenantDep = Annotated[UUID, Depends(require_tenant_id)]
# Quien hace la petición, garantizando que tiene ese permiso en su tenant
CanCreateClientsDep = Annotated[Principal, Depends(require_permission(Permission.CLIENTES_CREAR))]
CanReadClientsDep = Annotated[Principal, Depends(require_permission(Permission.CLIENTES_LEER))]
