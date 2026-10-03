from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.modules.clients.dependencies import ClientServiceDep, GroupServiceDep
from app.modules.clients.listing import CompanyFiltersDep
from app.modules.clients.schemas import (
    ClientCreate,
    ClientCreated,
    CompanyDetail,
    CompanyListItem,
    GroupIn,
    GroupListItem,
    GroupRead,
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
groups_router = APIRouter()  # /groups


@router.post(
    "",
    response_model=ApiResponse[ClientCreated],
    status_code=status.HTTP_201_CREATED,
    summary="Crear cliente (asistente 'Nuevo cliente')",
)
def create_client(
    data: ClientCreate,
    service: ClientServiceDep,
    actor: CanCreateClientsDep,
    organization: RequiredTenantDep,
):
    """Crea en una sola operación la empresa (el cliente) con su RUT, su grupo (uno
    existente con `group_id`, uno nuevo con `group_name`, o ninguno), los compromisos y
    los usuarios. Si algo falla, no se crea nada."""
    return ApiResponse(message="Client created", data=service.create(data, actor, organization))


# ── Catálogo de grupos (paso 1: elegir un grupo o agregarlo si no está) ─────


@groups_router.get(
    "", response_model=ApiResponse[list[GroupListItem]], summary="Buscar grupos de la firma"
)
def search_groups(
    service: GroupServiceDep,
    actor: CanCreateClientsDep,
    organization: RequiredTenantDep,
    q: Annotated[str | None, Query(max_length=100, description="Parte del nombre")] = None,
):
    """Grupos activos, con su número de empresas. La búsqueda no distingue mayúsculas,
    tildes ni espacios de más. Máximo 20."""
    return ApiResponse(data=service.search(organization, q))


@groups_router.post(
    "",
    response_model=ApiResponse[GroupRead],
    status_code=status.HTTP_201_CREATED,
    summary="Agregar un grupo al catálogo",
)
def create_group(
    data: GroupIn,
    service: GroupServiceDep,
    actor: CanCreateClientsDep,
    organization: RequiredTenantDep,
):
    """Si ya existe (escrito como sea), responde 409 con `details.group_id` del existente,
    para que el front ofrezca elegirlo."""
    group = service.create_and_commit(organization, data.name, actor)
    return ApiResponse(message="Group created", data=GroupRead.model_validate(group))


@groups_router.patch(
    "/{group_id}", response_model=ApiResponse[GroupRead], summary="Cambiar el nombre de un grupo"
)
def rename_group(
    group_id: UUID,
    data: GroupIn,
    service: GroupServiceDep,
    actor: CanCreateClientsDep,
    organization: RequiredTenantDep,
):
    group = service.rename(organization, group_id, data.name, actor)
    return ApiResponse(message="Group updated", data=GroupRead.model_validate(group))


@companies_router.get(
    "",
    response_model=ApiResponse[Page[CompanyListItem]],
    summary="Pantalla de clientes: una fila por empresa",
)
def list_companies(
    service: ClientServiceDep,
    actor: CanReadClientsDep,
    tenant: TenantDep,
    filters: CompanyFiltersDep,
    params: PageParamsDep,
):
    """Requiere `clientes.leer`. Cada rol ve su alcance: el Administrador, todas las de la
    organización; Socio y Gerente, las de sus compromisos; el Cliente, las empresas que
    tiene asignadas.

    Orden (`sort`): name, nit, group, active_engagements, rut_generated_at,
    rut_updated_at; con "-" es descendente. Por defecto, por nombre."""
    return ApiResponse(data=service.list_companies(actor, tenant, filters, params))


@companies_router.get(
    "/nit-check",
    response_model=ApiResponse[NitCheck],
    summary="¿El NIT ya está registrado en la organización? (paso 1)",
)
def check_nit(
    service: ClientServiceDep,
    actor: CanCreateClientsDep,
    organization: RequiredTenantDep,
    nit: Annotated[str, Query(pattern=r"^[0-9]{5,15}$", description="Sin dígito de verificación")],
):
    """Si existe, el front ofrece abrir la empresa existente en lugar de crear otra."""
    return ApiResponse(data=service.check_nit(organization, nit))


# Va después de /nit-check: si no, "nit-check" se tomaría como un company_id
@companies_router.get(
    "/{company_id}", response_model=ApiResponse[CompanyDetail], summary="Ficha de la empresa"
)
def get_company(
    company_id: UUID, service: ClientServiceDep, actor: CanReadClientsDep, tenant: TenantDep
):
    """Datos del RUT con sus dos fechas, datos de la organización, estado, grupo y demás
    empresas del grupo, compromisos, versiones del RUT (con los años que cubre) y usuarios
    del cliente. Requiere `clientes.leer`; fuera del alcance de quien consulta, 404."""
    return ApiResponse(data=service.get_detail(actor, tenant, company_id))
