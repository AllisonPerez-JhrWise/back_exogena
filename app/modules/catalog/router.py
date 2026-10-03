from uuid import UUID

from fastapi import APIRouter

from app.core.auth import CanReadClientsDep, OrganizationDep
from app.modules.catalog.dependencies import CatalogServiceDep
from app.modules.catalog.schemas import ObligationRead, OfferedServiceTypeRead, ServiceTypeRead
from app.shared.responses import ApiResponse

# Solo lectura: lo que se ofrece al crear compromisos. Requiere `clientes.crear` (basta
# el nivel Consulta) en la organización de X-Organization-Id. Administrarlo, después.
obligations_router = APIRouter()
service_types_router = APIRouter()


@obligations_router.get(
    "", response_model=ApiResponse[list[ObligationRead]], summary="Obligaciones activas"
)
def list_obligations(
    service: CatalogServiceDep, _: CanReadClientsDep, organization: OrganizationDep
):
    return ApiResponse(data=service.list_obligations(organization))


@obligations_router.get(
    "/{obligation_id}/service-types",
    response_model=ApiResponse[list[OfferedServiceTypeRead]],
    summary="Tipos de servicio que se ofrecen para una obligación",
)
def list_service_types_for_obligation(
    obligation_id: UUID,
    service: CatalogServiceDep,
    _: CanReadClientsDep,
    organization: OrganizationDep,
):
    """Solo los que tienen un servicio activo con esa obligación."""
    return ApiResponse(data=service.list_service_types_for(organization, obligation_id))


@service_types_router.get(
    "", response_model=ApiResponse[list[ServiceTypeRead]], summary="Tipos de servicio activos"
)
def list_service_types(
    service: CatalogServiceDep, _: CanReadClientsDep, organization: OrganizationDep
):
    return ApiResponse(data=service.list_service_types(organization))
