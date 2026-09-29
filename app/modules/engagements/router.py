from uuid import UUID

from fastapi import APIRouter, status

from app.modules.engagements.dependencies import EngagementServiceDep
from app.modules.engagements.schemas import EngagementIn, EngagementRead
from app.modules.platform.dependencies import CanCreateClientsDep, TenantDep
from app.shared.responses import ApiResponse

# Se monta bajo /companies: POST /companies/{company_id}/engagements
router = APIRouter()


@router.post(
    "/{company_id}/engagements",
    response_model=ApiResponse[EngagementRead],
    status_code=status.HTTP_201_CREATED,
    summary="Crear un compromiso de una empresa existente",
)
async def create_engagement(
    company_id: UUID,
    data: EngagementIn,
    service: EngagementServiceDep,
    actor: CanCreateClientsDep,
    tenant: TenantDep,
):
    """Requiere `clientes.crear` ("crear clientes y compromisos, y asignar socio y
    gerente"). Nace en estado `por_iniciar`."""
    return ApiResponse(
        message="Engagement created",
        data=await service.create_for_company(company_id, data, tenant, actor),
    )
