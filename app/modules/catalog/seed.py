"""Catálogo inicial de la firma: las obligaciones, tipos de servicio y servicios que
presta hoy (tarea "Catálogo de obligaciones y servicios").

No incluye lo que carga el proyecto de Saldos a Favor (tipo "Devolución de saldo a favor"
y su servicio con Declaración de renta). Lo demás (outsourcing contable, IVA, ICA...) lo
crea el Administrador cuando se necesite.

La carga se puede repetir: crea solo lo que falta (por nombre) y no cambia lo existente.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.catalog.models import Obligation, ObligationNature, Service, ServiceType

EXOGENA = "Información exógena"
RENTA = "Declaración de renta y complementarios"
PRECIOS = "Precios de transferencia"
ELABORACION = "Elaboración"
REVISION = "Revisión"

OBLIGATIONS = [
    (EXOGENA, "Reporte anual de información de terceros a la DIAN", ObligationNature.TRIBUTARIA),
    (
        RENTA,
        "Declaración anual del impuesto sobre la renta de personas jurídicas (formulario 110)",
        ObligationNature.TRIBUTARIA,
    ),
    # Todavía sin servicios
    (
        PRECIOS,
        "Declaración informativa y documentación comprobatoria de precios de transferencia",
        ObligationNature.TRIBUTARIA,
    ),
]

SERVICE_TYPES = [ELABORACION, REVISION]

SERVICES = [(EXOGENA, ELABORACION), (EXOGENA, REVISION), (RENTA, REVISION)]


@dataclass
class SeedResult:
    obligations: int = 0
    service_types: int = 0
    services: int = 0


def seed_catalog(session: Session, tenant_id: UUID, actor_id: UUID | None = None) -> SeedResult:
    """Crea en la organización lo que falte del catálogo inicial. No hace commit."""
    created = SeedResult()

    def find(model, name: str):
        return session.scalar(
            select(model).where(
                model.tenant_id == tenant_id,
                func.lower(model.name) == name.lower(),
                model.is_deleted.is_(False),
            )
        )

    obligations: dict[str, Obligation] = {}
    for name, description, nature in OBLIGATIONS:
        obligation = find(Obligation, name)
        if obligation is None:
            obligation = Obligation(
                tenant_id=tenant_id,
                name=name,
                description=description,
                nature=nature,
                created_by=actor_id,
            )
            session.add(obligation)
            created.obligations += 1
        obligations[name] = obligation

    service_types: dict[str, ServiceType] = {}
    for name in SERVICE_TYPES:
        service_type = find(ServiceType, name)
        if service_type is None:
            service_type = ServiceType(tenant_id=tenant_id, name=name, created_by=actor_id)
            session.add(service_type)
            created.service_types += 1
        service_types[name] = service_type
    session.flush()

    for obligation_name, type_name in SERVICES:
        obligation, service_type = obligations[obligation_name], service_types[type_name]
        exists = session.scalar(
            select(Service.id).where(
                Service.tenant_id == tenant_id,
                Service.obligation_id == obligation.id,
                Service.service_type_id == service_type.id,
                Service.is_deleted.is_(False),
            )
        )
        if exists is None:
            session.add(
                Service(
                    tenant_id=tenant_id,
                    obligation_id=obligation.id,
                    service_type_id=service_type.id,
                    created_by=actor_id,
                )
            )
            created.services += 1
    session.flush()
    return created
