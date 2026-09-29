"""Catálogo de obligaciones, tipos de servicio y servicios: lo que se lista al crear
compromisos y las reglas que protege la base de datos."""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings, settings
from app.modules.catalog.models import Obligation, ObligationNature, Service, ServiceType
from app.modules.catalog.seed import seed_catalog
from tests.integration.conftest import auth_headers


class Catalog:
    """Carga el catálogo de una organización (como superusuario, confirmando)."""

    def __init__(self, session, tenant_id):
        self.session = session
        self.tenant_id = tenant_id

    async def _save(self, obj):
        self.session.add(obj)
        await self.session.commit()
        return obj

    async def obligation(self, name, nature=ObligationNature.TRIBUTARIA, **extra):
        return await self._save(
            Obligation(tenant_id=self.tenant_id, name=name, nature=nature, **extra)
        )

    async def service_type(self, name, **extra):
        return await self._save(ServiceType(tenant_id=self.tenant_id, name=name, **extra))

    async def service(self, obligation, service_type, **extra):
        return await self._save(
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
async def asociado(staff):
    # Cualquier persona de la firma con clientes.leer puede consultar el catálogo
    return await staff("asociado@jhrwise.com")


async def test_lists_active_obligations_of_the_organization(
    client, asociado, catalog, platform, db_session
):
    await catalog.obligation(
        "Información exógena", description="Reporte anual de información de terceros a la DIAN"
    )
    await catalog.obligation("Outsourcing contable", ObligationNature.SERVICIO_RECURRENTE)
    await catalog.obligation("Precios de transferencia", is_active=False)
    # De otra organización: no se ve
    await Catalog(db_session, await platform.tenant("otra-firma")).obligation("Otra")

    response = await client.get("/api/v1/obligations", headers=asociado)

    assert response.status_code == 200, response.text
    assert [(o["name"], o["nature"], o["requires_due_date"]) for o in response.json()["data"]] == [
        ("Información exógena", "tributaria", True),
        ("Outsourcing contable", "servicio_recurrente", False),
    ]


async def test_service_types_depend_on_the_obligation(client, asociado, catalog):
    exogena = await catalog.obligation("Información exógena")
    renta = await catalog.obligation("Declaración de renta y complementarios")
    elaboracion = await catalog.service_type("Elaboración")
    revision = await catalog.service_type("Revisión")
    devolucion = await catalog.service_type("Devolución de saldo a favor")
    elaboracion_exogena = await catalog.service(exogena, elaboracion)
    await catalog.service(exogena, revision)
    await catalog.service(exogena, devolucion, is_active=False)  # servicio inactivo
    await catalog.service(renta, revision)

    response = await client.get(f"/api/v1/obligations/{exogena.id}/service-types", headers=asociado)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert [t["name"] for t in data] == ["Elaboración", "Revisión"]
    assert data[0]["service_id"] == str(elaboracion_exogena.id)

    # Todos los tipos de servicio activos, sin importar la obligación
    all_types = await client.get("/api/v1/service-types", headers=asociado)
    assert [t["name"] for t in all_types.json()["data"]] == [
        "Devolución de saldo a favor",
        "Elaboración",
        "Revisión",
    ]


async def test_inactive_service_type_is_not_offered(client, asociado, catalog):
    exogena = await catalog.obligation("Información exógena")
    revision = await catalog.service_type("Revisión", is_active=False)
    await catalog.service(exogena, revision)

    response = await client.get(f"/api/v1/obligations/{exogena.id}/service-types", headers=asociado)
    assert response.json()["data"] == []


async def test_inactive_or_foreign_obligation_is_not_found(
    client, asociado, catalog, platform, db_session
):
    inactive = await catalog.obligation("Precios de transferencia", is_active=False)
    foreign = await Catalog(db_session, await platform.tenant("otra-firma")).obligation("Otra")

    for obligation_id in (inactive.id, foreign.id, uuid4()):
        url = f"/api/v1/obligations/{obligation_id}/service-types"
        assert (await client.get(url, headers=asociado)).status_code == 404


async def test_requires_membership_in_the_tenant(client, platform, firm):
    outsider = auth_headers(await platform.user("externo@x.co"), firm)
    for url in ("/api/v1/obligations", "/api/v1/service-types"):
        assert (await client.get(url)).status_code == 401
        assert (await client.get(url, headers=outsider)).status_code == 403


# ── Modo de pruebas (AUTH_BYPASS) ──


@pytest.fixture
def auth_bypass(monkeypatch):
    monkeypatch.setattr(settings, "auth_bypass", True)
    # Sin firma por defecto (aunque el .env local tenga DEV_TENANT_ID): se ve todo
    monkeypatch.setattr(settings, "dev_tenant_id", None)


async def test_bypass_shows_everything_without_token_or_tenant(
    client, auth_bypass, catalog, platform, db_session
):
    await catalog.obligation("Información exógena")
    await Catalog(db_session, await platform.tenant("otra-firma")).obligation("Otra")

    response = await client.get("/api/v1/obligations")

    assert response.status_code == 200, response.text
    assert [o["name"] for o in response.json()["data"]] == ["Información exógena", "Otra"]


async def test_bypass_still_checks_a_tenant_when_it_is_sent(client, auth_bypass, platform, firm):
    outsider = auth_headers(await platform.user("externo@x.co"), firm)
    assert (await client.get("/api/v1/obligations", headers=outsider)).status_code == 403


def test_bypass_is_forbidden_in_production():
    with pytest.raises(ValueError, match="AUTH_BYPASS"):
        Settings(
            environment="production",
            auth_bypass=True,
            database_url="postgresql+asyncpg://u:p@h/db",
            jwt_secret="x" * 32,
        )


# ── Catálogo inicial de la firma ──


async def test_initial_catalog_can_be_loaded_twice(client, asociado, db_session, firm):
    first = await seed_catalog(db_session, firm)
    await db_session.commit()
    again = await seed_catalog(db_session, firm)
    await db_session.commit()

    assert (first.obligations, first.service_types, first.services) == (3, 2, 3)
    assert (again.obligations, again.service_types, again.services) == (0, 0, 0)

    obligations = (await client.get("/api/v1/obligations", headers=asociado)).json()["data"]
    assert [o["name"] for o in obligations] == [
        "Declaración de renta y complementarios",
        "Información exógena",
        "Precios de transferencia",
    ]
    offered = {}
    for obligation in obligations:
        url = f"/api/v1/obligations/{obligation['id']}/service-types"
        types = (await client.get(url, headers=asociado)).json()["data"]
        offered[obligation["name"]] = [t["name"] for t in types]
    assert offered == {
        "Declaración de renta y complementarios": ["Revisión"],
        "Información exógena": ["Elaboración", "Revisión"],
        "Precios de transferencia": [],
    }


# ── Reglas de la base de datos ──


async def assert_rejected(session, obj) -> None:
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(obj)
            await session.flush()


async def test_obligation_name_is_unique_per_organization(db_session, catalog, platform):
    await catalog.obligation("Información exógena")
    duplicate = Obligation(
        tenant_id=catalog.tenant_id, name="INFORMACIÓN EXÓGENA", nature=ObligationNature.TRIBUTARIA
    )
    await assert_rejected(db_session, duplicate)
    # Otra organización sí puede usar el mismo nombre
    await Catalog(db_session, await platform.tenant("otra-firma")).obligation("Información exógena")


async def test_obligation_nature_is_enforced(db_session, catalog):
    await assert_rejected(
        db_session, Obligation(tenant_id=catalog.tenant_id, name="Nómina", nature="mensual")
    )


async def test_service_is_unique_per_obligation_and_type(db_session, catalog):
    exogena = await catalog.obligation("Información exógena")
    elaboracion = await catalog.service_type("Elaboración")
    await catalog.service(exogena, elaboracion)
    await assert_rejected(
        db_session,
        Service(
            tenant_id=catalog.tenant_id,
            obligation_id=exogena.id,
            service_type_id=elaboracion.id,
        ),
    )
