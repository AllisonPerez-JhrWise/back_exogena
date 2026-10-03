"""Consulta de la pantalla de clientes: una fila por empresa, porque el trabajo y la
obligación son por NIT. El grupo, los compromisos activos y el estado se calculan."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import ColumnElement, Select, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.modules.clients.models import Company, CompanyStatus, Group
from app.modules.engagements.models import Engagement, EngagementStatus
from app.shared.pagination import PageParams

# Compromisos que cuentan como activos en la pantalla: todos menos los cerrados
ACTIVE_ENGAGEMENT_STATUSES = tuple(s for s in EngagementStatus if s != EngagementStatus.CLOSED)


_STATUS = "|".join(s.value for s in CompanyStatus)
# Uno o varios estados separados por coma: status=activo,rut_por_renovar
STATUS_PATTERN = rf"^({_STATUS})(,({_STATUS}))*$"


@dataclass
class CompanyFilters:
    """Filtros de la pantalla ("+ Agregar filtro")."""

    company: str | None = None
    nit: str | None = None
    group_id: UUID | None = None
    group: str | None = None
    engagements_min: int | None = None
    engagements_max: int | None = None
    statuses: list[CompanyStatus] = field(default_factory=list)
    # Uso interno (ficha de la empresa): no es un filtro de la pantalla
    company_id: UUID | None = None


def get_company_filters(
    company: Annotated[
        str | None, Query(max_length=100, description="Nombre de la empresa")
    ] = None,
    nit: Annotated[str | None, Query(pattern=r"^[0-9]{1,15}$", description="NIT o parte")] = None,
    group_id: Annotated[UUID | None, Query(description="Filtro Grupo: empresas del grupo")] = None,
    group: Annotated[str | None, Query(max_length=100, description="Nombre del grupo")] = None,
    engagements_min: Annotated[int | None, Query(ge=0, description="Compromisos activos")] = None,
    engagements_max: Annotated[int | None, Query(ge=0)] = None,
    status: Annotated[
        str | None,
        Query(pattern=STATUS_PATTERN, description="activo, inactivo, rut_por_renovar"),
    ] = None,
) -> CompanyFilters:
    # Parámetros sueltos (no un modelo): FastAPI no admite dos modelos de query en la
    # misma ruta, y la pantalla también recibe los de paginación
    return CompanyFilters(
        company=company,
        nit=nit,
        group_id=group_id,
        group=group,
        engagements_min=engagements_min,
        engagements_max=engagements_max,
        statuses=[CompanyStatus(s) for s in status.split(",")] if status else [],
    )


CompanyFiltersDep = Annotated[CompanyFilters, Depends(get_company_filters)]


@dataclass
class CompanyScope:
    """Qué empresas puede ver quien consulta (alcance de la tarea, F0-02, según Identidad)."""

    organization_id: UUID | None = None  # la firma
    # None = todas las de la organización (el Administrador). Si no, solo estas: las de
    # sus compromisos y las que tiene asignadas
    company_ids: frozenset[UUID] | None = None


@dataclass
class CompanyRow:
    company: Company
    group: str | None
    active_engagements: int
    status: CompanyStatus


def _display_name():
    """Nombre para mostrar en SQL (razón social o nombre completo), para buscar y ordenar."""
    return func.coalesce(
        Company.legal_name,
        func.concat_ws(
            " ",
            Company.first_name,
            Company.middle_name,
            Company.last_name,
            Company.second_last_name,
        ),
    )


def _columns():
    active_engagements = (
        select(func.count(Engagement.id))
        .where(
            Engagement.company_id == Company.id,
            Engagement.is_deleted.is_(False),
            Engagement.status.in_(ACTIVE_ENGAGEMENT_STATUSES),
        )
        .scalar_subquery()
    )
    renewal_limit = func.current_date() - func.make_interval(0, settings.rut_renewal_months)
    status = case(
        (Company.is_active.is_(False), CompanyStatus.INACTIVO.value),
        (
            or_(Company.rut_generated_at.is_(None), Company.rut_generated_at < renewal_limit),
            CompanyStatus.RUT_POR_RENOVAR.value,
        ),
        else_=CompanyStatus.ACTIVO.value,
    )
    return Group.name, active_engagements, status


SORTABLE = ("name", "nit", "group", "active_engagements", "rut_generated_at", "rut_updated_at")


def list_companies(
    session: Session, scope: CompanyScope, filters: CompanyFilters, params: PageParams
) -> tuple[Sequence[CompanyRow], int]:
    group, active_engagements, status = _columns()
    query: Select = (
        select(Company, group, active_engagements, status)
        # El grupo es opcional: las empresas sin grupo también se listan
        .outerjoin(Group, Group.id == Company.group_id)
        .where(Company.is_deleted.is_(False))
    )
    query = query.where(
        *_scope_conditions(scope), *_filter_conditions(filters, group, active_engagements, status)
    )

    total = session.scalar(select(func.count()).select_from(query.subquery()))
    order = _order_by(params.sort or "name", group, active_engagements)
    result = session.execute(query.order_by(*order).offset(params.offset).limit(params.size))
    rows = [
        CompanyRow(company=c, group=g, active_engagements=n, status=CompanyStatus(s))
        for c, g, n, s in result.tuples().all()
    ]
    return rows, total or 0


def _scope_conditions(scope: CompanyScope) -> list[ColumnElement[bool]]:
    conditions = []
    if scope.organization_id:
        conditions.append(Company.organization_id == scope.organization_id)
    if scope.company_ids is not None:
        conditions.append(Company.id.in_(scope.company_ids))
    return conditions


def _filter_conditions(filters: CompanyFilters, group, active_engagements, status):
    conditions = []
    if filters.company_id:
        conditions.append(Company.id == filters.company_id)
    if filters.company:
        pattern = f"%{filters.company.strip()}%"
        conditions.append(or_(_display_name().ilike(pattern), Company.trade_name.ilike(pattern)))
    if filters.nit:
        conditions.append(Company.nit.contains(filters.nit))
    if filters.group_id:
        conditions.append(Company.group_id == filters.group_id)
    if filters.group:
        conditions.append(Group.name.ilike(f"%{filters.group.strip()}%"))
    if filters.engagements_min is not None:
        conditions.append(active_engagements >= filters.engagements_min)
    if filters.engagements_max is not None:
        conditions.append(active_engagements <= filters.engagements_max)
    if filters.statuses:
        conditions.append(status.in_([s.value for s in filters.statuses]))
    return conditions


def _order_by(sort: str, group, active_engagements) -> list:
    field = sort.lstrip("-")
    columns = {
        "name": func.lower(_display_name()),
        "nit": Company.nit,
        "group": func.lower(group),
        "active_engagements": active_engagements,
        "rut_generated_at": Company.rut_generated_at,
        "rut_updated_at": Company.rut_updated_at,
    }
    if field not in columns:
        raise BadRequestError(f"Cannot sort by '{field}'", details={"allowed": sorted(SORTABLE)})
    column = columns[field]
    ordered = column.desc().nulls_last() if sort.startswith("-") else column.asc().nulls_last()
    # id como desempate mantiene estable la paginación
    return [ordered, Company.id]
