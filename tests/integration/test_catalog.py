"""Catálogo de obligaciones, tipos de servicio y servicios: lo que se lista al crear
compromisos y las reglas que protege la base de datos."""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings, settings
from app.core.dev_access import enable_dev_access
from app.main import app
from app.modules.catalog.models import Obligation, ObligationNature, Service, ServiceType
from app.modules.catalog.seed import seed_catalog
from tests.integration.conftest import auth_headers
from tests.integration.identity import SystemRole


class Catalog:
    """Carga el catálogo de una organización (como superusuario, confirmando)."""

    def __init__(self, session, tenant_id):
        self.session = session
        self.tenant_id = tenant_id

    def _save(self, obj):
        self.session.add(obj)
        self.session.commit()
        return obj

    def obligation(self, name, nature=ObligationNature.TRIBUTARIA, **extra):
        return self._save(Obligation(tenant_id=self.tenant_id, name=name, nature=nature, **extra))

    def service_type(self, name, **extra):
        return self._save(ServiceType(tenant_id=self.tenant_id, name=name, **extra))

    def service(self, obligation, service_type, **extra):
        return self._save(
            Service(
                tenant_id=self.tenant_id,
                obligation_id=obligation.id,
                service_type_id=service_type.id,
                **extra,
            )
        )


@pytest.fixture
def catalog(db_session, firm) -> Catalog:
    return Catalog(db_session, firm)


@pytest.fixture
def asociado(staff):
    # Quien tenga clientes.crear en alguna parte (aunque sea en Consulta) consulta el
    # catálogo. El Administrador lo usa en el asistente "Nuevo cliente"
    return staff("admin@jhrwise.com", SystemRole.ADMINISTRADOR)


def test_lists_active_obligations_of_the_organization(
    client, asociado, catalog, platform, db_session
):
    catalog.obligation(
        "Información exógena", description="Reporte anual de información de terceros a la DIAN"
    )
    catalog.obligation("Outsourcing contable", ObligationNature.SERVICIO_RECURRENTE)
    catalog.obligation("Precios de transferencia", is_active=False)
    # De otra organización: no se ve
    Catalog(db_session, platform.tenant("otra-firma")).obligation("Otra")

    response = client.get("/api/v1/obligations", headers=asociado)

    assert response.status_code == 200, response.text
    assert [(o["name"], o["nature"], o["requires_due_date"]) for o in response.json()["data"]] == [
        ("Información exógena", "tributaria", True),
        ("Outsourcing contable", "servicio_recurrente", False),
    ]


def test_service_types_depend_on_the_obligation(client, asociado, catalog):
    exogena = catalog.obligation("Información exógena")
    renta = catalog.obligation("Declaración de renta y complementarios")
    elaboracion = catalog.service_type("Elaboración")
    revision = catalog.service_type("Revisión")
    devolucion = catalog.service_type("Devolución de saldo a favor")
    elaboracion_exogena = catalog.service(exogena, elaboracion)
    catalog.service(exogena, revision)
    catalog.service(exogena, devolucion, is_active=False)  # servicio inactivo
    catalog.service(renta, revision)

    response = client.get(f"/api/v1/obligations/{exogena.id}/service-types", headers=asociado)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert [t["name"] for t in data] == ["Elaboración", "Revisión"]
    assert data[0]["service_id"] == str(elaboracion_exogena.id)

    # Todos los tipos de servicio activos, sin importar la obligación
    all_types = client.get("/api/v1/service-types", headers=asociado)
    assert [t["name"] for t in all_types.json()["data"]] == [
        "Devolución de saldo a favor",
        "Elaboración",
        "Revisión",
    ]


def test_inactive_service_type_is_not_offered(client, asociado, catalog):
    exogena = catalog.obligation("Información exógena")
    revision = catalog.service_type("Revisión", is_active=False)
    catalog.service(exogena, revision)

    response = client.get(f"/api/v1/obligations/{exogena.id}/service-types", headers=asociado)
    assert response.json()["data"] == []


def test_inactive_or_foreign_obligation_is_not_found(
    client, asociado, catalog, platform, db_session
):
    inactive = catalog.obligation("Precios de transferencia", is_active=False)
    foreign = Catalog(db_session, platform.tenant("otra-firma")).obligation("Otra")

    for obligation_id in (inactive.id, foreign.id, uuid4()):
        url = f"/api/v1/obligations/{obligation_id}/service-types"
        assert (client.get(url, headers=asociado)).status_code == 404


def test_requires_membership_and_a_permission(client, platform, firm, staff):
    outsider = auth_headers(platform.user("externo@x.co"), firm)
    # Un asociado sin compromisos asignados no tiene el permiso en ninguna parte
    asociado = staff("asociado@jhrwise.com", SystemRole.ASOCIADO)
    for url in ("/api/v1/obligations", "/api/v1/service-types"):
        assert (client.get(url)).status_code == 401
        assert (client.get(url, headers=outsider)).status_code == 403
        assert (client.get(url, headers=asociado)).status_code == 403


def test_organization_header_is_required(client, platform, firm):
    admin_id = platform.user("admin@jhrwise.com")
    platform.member(admin_id, firm, SystemRole.ADMINISTRADOR)
    response = client.get("/api/v1/obligations", headers=auth_headers(admin_id))
    assert response.status_code == 400


# ── Modo de desarrollo local (AUTH_BYPASS) ──


@pytest.fixture
def dev_mode(client, monkeypatch, firm):
    """Como con AUTH_BYPASS=true en local: sin token, Administrador de la firma."""
    monkeypatch.setattr(settings, "dev_organization_id", firm)
    enable_dev_access(app)  # el fixture client deshace todo al terminar


def test_dev_mode_works_without_token(client, dev_mode, catalog, platform, db_session):
    catalog.obligation("Información exógena")
    other = platform.tenant("otra-firma")
    Catalog(db_session, other).obligation("Otra")

    # Sin encabezados: la firma de DEV_ORGANIZATION_ID
    response = client.get("/api/v1/obligations")
    assert response.status_code == 200, response.text
    assert [o["name"] for o in response.json()["data"]] == ["Información exógena"]

    # Con X-Organization-Id: esa organización
    response = client.get("/api/v1/obligations", headers={"X-Organization-Id": str(other)})
    assert [o["name"] for o in response.json()["data"]] == ["Otra"]


def test_bypass_is_forbidden_in_production():
    with pytest.raises(ValueError, match="AUTH_BYPASS"):
        Settings(
            environment="production",
            auth_bypass=True,
            jwt_secret="x" * 32,
        )


# ── Catálogo inicial de la firma ──


def test_initial_catalog_can_be_loaded_twice(client, asociado, db_session, firm):
    first = seed_catalog(db_session, firm)
    db_session.commit()
    again = seed_catalog(db_session, firm)
    db_session.commit()

    assert (first.obligations, first.service_types, first.services) == (3, 2, 3)
    assert (again.obligations, again.service_types, again.services) == (0, 0, 0)

    obligations = (client.get("/api/v1/obligations", headers=asociado)).json()["data"]
    assert [o["name"] for o in obligations] == [
        "Declaración de renta y complementarios",
        "Información exógena",
        "Precios de transferencia",
    ]
    offered = {}
    for obligation in obligations:
        url = f"/api/v1/obligations/{obligation['id']}/service-types"
        types = (client.get(url, headers=asociado)).json()["data"]
        offered[obligation["name"]] = [t["name"] for t in types]
    assert offered == {
        "Declaración de renta y complementarios": ["Revisión"],
        "Información exógena": ["Elaboración", "Revisión"],
        "Precios de transferencia": [],
    }


# ── Reglas de la base de datos ──


def assert_rejected(session, obj) -> None:
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(obj)
        session.flush()


def test_obligation_name_is_unique_per_organization(db_session, catalog, platform):
    catalog.obligation("Información exógena")
    duplicate = Obligation(
        tenant_id=catalog.tenant_id, name="INFORMACIÓN EXÓGENA", nature=ObligationNature.TRIBUTARIA
    )
    assert_rejected(db_session, duplicate)
    # Otra organización sí puede usar el mismo nombre
    Catalog(db_session, platform.tenant("otra-firma")).obligation("Información exógena")


def test_obligation_nature_is_enforced(db_session, catalog):
    assert_rejected(
        db_session, Obligation(tenant_id=catalog.tenant_id, name="Nómina", nature="mensual")
    )


def test_service_is_unique_per_obligation_and_type(db_session, catalog):
    exogena = catalog.obligation("Información exógena")
    elaboracion = catalog.service_type("Elaboración")
    catalog.service(exogena, elaboracion)
    assert_rejected(
        db_session,
        Service(
            tenant_id=catalog.tenant_id,
            obligation_id=exogena.id,
            service_type_id=elaboracion.id,
        ),
    )
