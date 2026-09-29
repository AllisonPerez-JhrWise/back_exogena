from typing import Annotated

from fastapi import APIRouter, Query, status

from app.modules.clients.dependencies import ClientServiceDep
from app.modules.clients.listing import CompanyFiltersDep
from app.modules.clients.schemas import (
    ClientCreate,
    ClientCreated,
    ClientSearchItem,
    CompanyListItem,
    NitCheck,
)
from app.modules.platform.dependencies import (
    CanCreateClientsDep,
    CanReadClientsDep,
    RequiredTenantDep,
    TenantDep,
)
from app.shared.pagination import Page, PageParamsDep
from app.shared.responses import ApiResponse

# Todo lo del asistente "Nuevo cliente" requiere `clientes.crear` en la organización
# del encabezado X-Tenant-Id (la firma)
router = APIRouter()  # /clients
companies_router = APIRouter()  # /companies


@router.post(
    "",
    response_model=ApiResponse[ClientCreated],
    status_code=status.HTTP_201_CREATED,
    summary="Crear cliente (asistente 'Nuevo cliente')",
)
async def create_client(
    data: ClientCreate,
    service: ClientServiceDep,
    actor: CanCreateClientsDep,
    organization: RequiredTenantDep,
):
    """Crea en una sola operación el cliente (o usa el existente de `client_id`), la
    empresa con su RUT, los compromisos y los usuarios. Si algo falla, no se crea nada."""
    return ApiResponse(
        message="Client created", data=await service.create(data, actor, organization)
    )


@router.get(
    "/search",
    response_model=ApiResponse[list[ClientSearchItem]],
    summary="Buscar clientes para 'Agregar a un cliente existente' (paso 1)",
)
async def search_clients(
    service: ClientServiceDep,
    actor: CanCreateClientsDep,
    organization: RequiredTenantDep,
    q: Annotated[str | None, Query(max_length=100, description="Nombre, empresa o NIT")] = None,
):
    """Clientes activos de la organización, con sus datos de contacto para proponerlos en
    el paso 2."""
    return ApiResponse(data=await service.search(organization, q))


@companies_router.get(
    "",
    response_model=ApiResponse[Page[CompanyListItem]],
    summary="Pantalla de clientes: una fila por empresa",
)
async def list_companies(
    service: ClientServiceDep,
    actor: CanReadClientsDep,
    tenant: TenantDep,
    filters: CompanyFiltersDep,
    params: PageParamsDep,
):
    """Requiere `clientes.leer`. Cada rol ve su alcance: el Administrador, todas las de la
    organización; Socio y Gerente, las de sus compromisos; el Cliente (con el X-Tenant-Id
    de su cuenta), solo las suyas.

    Orden (`sort`): name, nit, group, active_engagements, rut_generated_at,
    rut_updated_at; con "-" es descendente. Por defecto, por nombre."""
    return ApiResponse(data=await service.list_companies(actor, tenant, filters, params))


@companies_router.get(
    "/nit-check",
    response_model=ApiResponse[NitCheck],
    summary="¿El NIT ya está registrado en la organización? (paso 1)",
)
async def check_nit(
    service: ClientServiceDep,
    actor: CanCreateClientsDep,
    organization: RequiredTenantDep,
    nit: Annotated[str, Query(pattern=r"^[0-9]{5,15}$", description="Sin dígito de verificación")],
):
    """Si existe, el front ofrece abrir la empresa existente en lugar de crear otra."""
    return ApiResponse(data=await service.check_nit(organization, nit))
