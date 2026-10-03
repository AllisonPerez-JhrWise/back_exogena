from uuid import UUID

from fastapi import APIRouter, status

from app.core.auth import CanCreateClientsDep, CanReadClientsDep, OrganizationDep, PrincipalDep
from app.core.exceptions import NotFoundError
from app.core.identity import IdentityDep
from app.modules.clients.dependencies import ClientServiceDep
from app.modules.engagements.dependencies import EngagementServiceDep
from app.modules.engagements.schemas import EngagementIn, EngagementRead, EngagementSummary
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
def create_engagement(
    company_id: UUID,
    data: EngagementIn,
    service: EngagementServiceDep,
    actor: PrincipalDep,
    decision: CanCreateClientsDep,
    organization: OrganizationDep,
    identity: IdentityDep,
):
    """Requiere `clientes.crear` ("crear clientes y compromisos, y asignar socio y
    gerente") sobre esa empresa. Nace en estado `created`, con el socio y el gerente
    registrados en Identidad (si alguno no es de la firma: 422; si Identidad no responde:
    503; en ambos casos no se guarda nada)."""
    if not decision.cubre(empresa_id=company_id):
        raise NotFoundError("Company not found")
    return ApiResponse(
        message="Engagement created",
        data=service.create_for_company(company_id, data, organization, actor, identity),
    )


@engagements_router.get(
    "/{engagement_id}",
    response_model=ApiResponse[EngagementSummary],
    summary="Un compromiso, con su tipo de servicio",
)
def get_engagement(
    engagement_id: UUID,
    service: EngagementServiceDep,
    clients: ClientServiceDep,
    decision: CanReadClientsDep,
    organization: OrganizationDep,
):
    """Requiere `clientes.crear` (basta Consulta). Con el mismo alcance que la ficha de
    la empresa: si quien consulta no puede ver la empresa del compromiso, 404 (no 403,
    para no confirmar que existe)."""
    engagement = service.get(engagement_id, organization)
    clients.ensure_visible(decision, organization, engagement.company_id)
    return ApiResponse(data=engagement)
