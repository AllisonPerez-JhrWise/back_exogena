from uuid import UUID

from fastapi import APIRouter, status

from app.modules.clients.dependencies import ClientServiceDep
from app.modules.engagements.dependencies import EngagementServiceDep
from app.modules.engagements.schemas import EngagementIn, EngagementRead, EngagementSummary
from app.modules.platform.dependencies import CanCreateClientsDep, CanReadClientsDep, TenantDep
from app.shared.responses import ApiResponse

# Se monta bajo /companies: POST /companies/{company_id}/engagements
router = APIRouter()
# Se monta bajo /engagements: GET /engagements/{engagement_id}
engagements_router = APIRouter()


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


@engagements_router.get(
    "/{engagement_id}",
    response_model=ApiResponse[EngagementSummary],
    summary="Un compromiso, con su obligación y su tipo de servicio",
)
async def get_engagement(
    engagement_id: UUID,
    service: EngagementServiceDep,
    clients: ClientServiceDep,
    actor: CanReadClientsDep,
    tenant: TenantDep,
):
    """Requiere `clientes.leer`. Con el mismo alcance que la ficha de la empresa: si
    quien consulta no puede ver la empresa del compromiso, 404 (no 403, para no
    confirmar que existe)."""
    engagement = await service.get(engagement_id, tenant)
    await clients.ensure_visible(actor, tenant, engagement.company_id)
    return ApiResponse(data=engagement)
