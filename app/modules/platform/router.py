from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.database import SessionDep
from app.modules.platform.dependencies import CanCreateClientsDep, RequiredTenantDep
from app.modules.platform.models import SystemRole
from app.modules.platform.repository import PlatformRepository
from app.shared.responses import ApiResponse

router = APIRouter()


class MemberRead(BaseModel):
    user_id: UUID
    full_name: str
    email: str


@router.get(
    "",
    response_model=ApiResponse[list[MemberRead]],
    summary="Personas de la organización con un rol (p. ej. socios y gerentes)",
)
def list_members(
    role: SystemRole, session: SessionDep, actor: CanCreateClientsDep, tenant: RequiredTenantDep
):
    """Para los selectores de socio y gerente al crear compromisos: GET /members?role=socio.
    Solo membresías activas. Requiere `clientes.crear` (incluye asignar socio y gerente)."""
    users = PlatformRepository(session).list_members_with_role(tenant, role)
    return ApiResponse(
        data=[MemberRead(user_id=u.id, full_name=u.full_name or "", email=u.email) for u in users]
    )
