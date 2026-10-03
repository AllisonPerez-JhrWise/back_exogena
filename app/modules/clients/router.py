from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.core.auth import (
    CanCreateClientsDep,
    CanReadClientsDep,
    OrganizationDep,
    PrincipalDep,
    require_whole_organization,
)
from app.core.identity import IdentityDep
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
from app.shared.pagination import Page, PageParamsDep
from app.shared.responses import ApiResponse

# Todo lo del asistente "Nuevo cliente" requiere `clientes.crear` sobre toda la
# organización del encabezado X-Organization-Id (la firma): en la matriz inicial, el
# Administrador
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
    actor: PrincipalDep,
    decision: CanCreateClientsDep,
    organization: OrganizationDep,
    identity: IdentityDep,
):
    """Crea en una sola operación la empresa (el cliente) con su RUT, su grupo (uno
    existente con `group_id`, uno nuevo con `group_name`, o ninguno), los compromisos y
    los usuarios. Si algo falla, no se crea nada."""
    require_whole_organization(decision)
    return ApiResponse(
        message="Client created", data=service.create(data, actor, organization, identity)
    )


# ── Catálogo de grupos (paso 1: elegir un grupo o agregarlo si no está) ─────


@groups_router.get(
    "", response_model=ApiResponse[list[GroupListItem]], summary="Buscar grupos de la firma"
)
def search_groups(
    service: GroupServiceDep,
    actor: PrincipalDep,
    decision: CanCreateClientsDep,
    organization: OrganizationDep,
    q: Annotated[str | None, Query(max_length=100, description="Parte del nombre")] = None,
):
    """Grupos activos, con su número de empresas. La búsqueda no distingue mayúsculas,
    tildes ni espacios de más. Máximo 20."""
    require_whole_organization(decision)
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
    actor: PrincipalDep,
    decision: CanCreateClientsDep,
    organization: OrganizationDep,
):
    """Si ya existe (escrito como sea), responde 409 con `details.group_id` del existente,
    para que el front ofrezca elegirlo."""
    require_whole_organization(decision)
    group = service.create_and_commit(organization, data.name, actor)
    return ApiResponse(message="Group created", data=GroupRead.model_validate(group))


@groups_router.patch(
    "/{group_id}", response_model=ApiResponse[GroupRead], summary="Cambiar el nombre de un grupo"
)
def rename_group(
    group_id: UUID,
    data: GroupIn,
    service: GroupServiceDep,
    actor: PrincipalDep,
    decision: CanCreateClientsDep,
    organization: OrganizationDep,
):
    require_whole_organization(decision)
    group = service.rename(organization, group_id, data.name, actor)
    return ApiResponse(message="Group updated", data=GroupRead.model_validate(group))


@companies_router.get(
    "",
    response_model=ApiResponse[Page[CompanyListItem]],
    summary="Pantalla de clientes: una fila por empresa",
)
def list_companies(
    service: ClientServiceDep,
    decision: CanReadClientsDep,
    organization: OrganizationDep,
    filters: CompanyFiltersDep,
    params: PageParamsDep,
):
    """Requiere `clientes.crear` (basta el nivel Consulta). Cada quien ve su alcance según
    Identidad: el Administrador, todas las de la organización; Socio, Gerente, Senior y
    Asociado, las de sus compromisos; el Cliente, las empresas que tiene asignadas.

    Orden (`sort`): name, nit, group, active_engagements, rut_generated_at,
    rut_updated_at; con "-" es descendente. Por defecto, por nombre."""
    return ApiResponse(data=service.list_companies(decision, organization, filters, params))


@companies_router.get(
    "/nit-check",
    response_model=ApiResponse[NitCheck],
    summary="¿El NIT ya está registrado en la organización? (paso 1)",
)
def check_nit(
    service: ClientServiceDep,
    actor: PrincipalDep,
    decision: CanCreateClientsDep,
    organization: OrganizationDep,
    nit: Annotated[str, Query(pattern=r"^[0-9]{5,15}$", description="Sin dígito de verificación")],
):
    """Si existe, el front ofrece abrir la empresa existente en lugar de crear otra."""
    require_whole_organization(decision)
    return ApiResponse(data=service.check_nit(organization, nit))


# Va después de /nit-check: si no, "nit-check" se tomaría como un company_id
@companies_router.get(
    "/{company_id}", response_model=ApiResponse[CompanyDetail], summary="Ficha de la empresa"
)
def get_company(
    company_id: UUID,
    service: ClientServiceDep,
    decision: CanReadClientsDep,
    organization: OrganizationDep,
):
    """Datos del RUT con sus dos fechas, datos de la organización, estado, grupo y demás
    empresas del grupo, compromisos, versiones del RUT (con los años que cubre) y usuarios
    del cliente. Requiere `clientes.crear` (basta Consulta); fuera del alcance, 404."""
    return ApiResponse(data=service.get_detail(decision, organization, company_id))
