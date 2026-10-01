from uuid import UUID

from fastapi import APIRouter

from app.modules.catalog.dependencies import CatalogServiceDep
from app.modules.catalog.schemas import ObligationRead, OfferedServiceTypeRead, ServiceTypeRead
from app.modules.platform.dependencies import CanReadClientsDep, TenantDep
from app.shared.responses import ApiResponse

# Solo lectura: lo que se ofrece al crear compromisos. Requiere `clientes.leer` en el
# tenant del encabezado X-Tenant-Id. Administrar el catálogo se agrega después.
obligations_router = APIRouter()
service_types_router = APIRouter()


@obligations_router.get(
    "", response_model=ApiResponse[list[ObligationRead]], summary="Obligaciones activas"
)
async def list_obligations(service: CatalogServiceDep, actor: CanReadClientsDep, tenant: TenantDep):
    return ApiResponse(data=await service.list_obligations(tenant))


@obligations_router.get(
    "/{obligation_id}/service-types",
    response_model=ApiResponse[list[OfferedServiceTypeRead]],
    summary="Tipos de servicio que se ofrecen para una obligación",
)
async def list_service_types_for_obligation(
    obligation_id: UUID, service: CatalogServiceDep, actor: CanReadClientsDep, tenant: TenantDep
):
    """Solo los que tienen un servicio activo con esa obligación."""
    return ApiResponse(data=await service.list_service_types_for(tenant, obligation_id))


@service_types_router.get(
    "", response_model=ApiResponse[list[ServiceTypeRead]], summary="Tipos de servicio activos"
)
async def list_service_types(
    service: CatalogServiceDep, actor: CanReadClientsDep, tenant: TenantDep
):
    return ApiResponse(data=await service.list_service_types(tenant))
