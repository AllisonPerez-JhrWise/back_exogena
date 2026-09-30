"""Compromisos: se crean en el paso 3 de "Nuevo cliente" (POST /clients) o después
(POST /companies/{id}/engagements), con socio y gerente de la firma."""

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.modules.catalog.models import ObligationNature
from app.modules.clients.models import Company
from app.modules.engagements.models import Engagement
from app.modules.platform.models import MembershipStatus, SystemRole
from tests.integration.conftest import auth_headers
from tests.integration.test_catalog import Catalog
from tests.integration.test_create_client import URL as CLIENTS_URL
from tests.integration.test_create_client import payload


@dataclass
class Firm:
    """La firma con su catálogo y su equipo, lista para crear compromisos."""

    socio: UUID
    gerente: UUID
    exogena_elaboracion: UUID  # servicio de obligación tributaria
    outsourcing_elaboracion: UUID  # servicio de obligación de servicio recurrente


@pytest.fixture
async def team(db_session, platform, firm) -> Firm:
    catalog = Catalog(db_session, firm)
    exogena = await catalog.obligation("Información exógena")
    outsourcing = await catalog.obligation(
        "Outsourcing contable", ObligationNature.SERVICIO_RECURRENTE
    )
    elaboracion = await catalog.service_type("Elaboración")

    socio = await platform.user("juan.restrepo@jhrwise.com", "Juan Restrepo")
    await platform.member(socio, firm, SystemRole.SOCIO)
    gerente = await platform.user("maria.gomez@jhrwise.com", "María Gómez")
    await platform.member(gerente, firm, SystemRole.GERENTE)
    return Firm(
        socio=socio,
        gerente=gerente,
        exogena_elaboracion=(await catalog.service(exogena, elaboracion)).id,
        outsourcing_elaboracion=(await catalog.service(outsourcing, elaboracion)).id,
    )


def engagement(team: Firm, **changes) -> dict:
    data = {
        "service_id": str(team.exogena_elaboracion),
        "fiscal_year": 2025,
        "due_date": "2026-05-15",
        "partner_user_id": str(team.socio),
        "manager_user_id": str(team.gerente),
    }
    return {**data, **{k: str(v) if isinstance(v, UUID) else v for k, v in changes.items()}}


async def count(session, model=Engagement) -> int:
    return await session.scalar(select(func.count()).select_from(model))


async def create_client(client, admin, **changes) -> dict:
    response = await client.post(CLIENTS_URL, json=payload(**changes), headers=admin)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_client_is_created_with_its_engagements(client, admin, team, db_session):
    body = payload()
    body["engagements"] = [
        engagement(team),
        engagement(team, service_id=team.outsourcing_elaboracion, due_date=None),
    ]

    response = await client.post(CLIENTS_URL, json=body, headers=admin)

    assert response.status_code == 201, response.text
    created = response.json()["data"]["engagements"]
    assert [
        (
            e["obligation"]["name"],
            e["service_type"]["name"],
            e["fiscal_year"],
            e["due_date"],
            e["status"],
            e["partner"]["full_name"],
            e["manager"]["full_name"],
        )
        for e in created
    ] == [
        ("Información exógena", "Elaboración", 2025, "2026-05-15", "por_iniciar",
         "Juan Restrepo", "María Gómez"),
        ("Outsourcing contable", "Elaboración", 2025, None, "por_iniciar",
         "Juan Restrepo", "María Gómez"),
    ]  # fmt: skip
    assert await count(db_session) == 2


async def test_engagements_step_is_optional(client, admin, db_session):
    data = await create_client(client, admin)
    assert data["engagements"] == []
    assert await count(db_session) == 0


async def test_engagement_is_added_to_an_existing_company(client, admin, team):
    company_id = (await create_client(client, admin))["company"]["id"]

    response = await client.post(
        f"/api/v1/companies/{company_id}/engagements", json=engagement(team), headers=admin
    )

    assert response.status_code == 201, response.text
    assert response.json()["data"]["company_id"] == company_id
    assert response.json()["data"]["status"] == "por_iniciar"


async def test_tributaria_requires_due_date(client, admin, team, db_session):
    company_id = (await create_client(client, admin))["company"]["id"]
    url = f"/api/v1/companies/{company_id}/engagements"

    response = await client.post(url, json=engagement(team, due_date=None), headers=admin)

    assert response.status_code == 422
    assert response.json()["details"] == {"engagement": 0, "field": "due_date"}
    assert await count(db_session) == 0


@pytest.mark.parametrize(
    "changes, field",
    [
        ({"partner_user_id": "gerente"}, "partner_user_id"),  # un gerente como socio
        ({"manager_user_id": "socio"}, "manager_user_id"),  # un socio como gerente
        ({"partner_user_id": "nadie"}, "partner_user_id"),
        ({"service_id": "nadie"}, "service_id"),
    ],
    ids=["socio-sin-rol", "gerente-sin-rol", "socio-inexistente", "servicio-inexistente"],
)
async def test_team_and_service_are_validated(client, admin, team, changes, field):
    people = {"socio": team.socio, "gerente": team.gerente, "nadie": uuid4()}
    company_id = (await create_client(client, admin))["company"]["id"]

    response = await client.post(
        f"/api/v1/companies/{company_id}/engagements",
        json=engagement(team, **{k: people[v] for k, v in changes.items()}),
        headers=admin,
    )

    assert response.status_code == 422
    assert response.json()["details"]["field"] == field


async def test_revoked_partner_is_rejected(client, admin, team, platform, firm):
    ex_socio = await platform.user("ex.socio@jhrwise.com")
    await platform.member(ex_socio, firm, SystemRole.SOCIO, MembershipStatus.REVOKED)
    company_id = (await create_client(client, admin))["company"]["id"]

    response = await client.post(
        f"/api/v1/companies/{company_id}/engagements",
        json=engagement(team, partner_user_id=ex_socio),
        headers=admin,
    )
    assert response.status_code == 422


async def test_service_of_another_organization_is_rejected(
    client, admin, team, db_session, platform
):
    other = Catalog(db_session, await platform.tenant("otra-firma"))
    foreign = await other.service(
        await other.obligation("Información exógena"), await other.service_type("Revisión")
    )
    company_id = (await create_client(client, admin))["company"]["id"]

    response = await client.post(
        f"/api/v1/companies/{company_id}/engagements",
        json=engagement(team, service_id=foreign.id),
        headers=admin,
    )
    assert response.status_code == 422
    assert response.json()["details"]["field"] == "service_id"


async def test_same_service_and_year_is_not_repeated(client, admin, team):
    company_id = (await create_client(client, admin))["company"]["id"]
    url = f"/api/v1/companies/{company_id}/engagements"

    assert (await client.post(url, json=engagement(team), headers=admin)).status_code == 201
    again = await client.post(url, json=engagement(team), headers=admin)
    assert again.status_code == 409

    # Otro año gravable sí
    other_year = engagement(team, fiscal_year=2026, due_date="2027-05-15")
    assert (await client.post(url, json=other_year, headers=admin)).status_code == 201


async def test_repeated_engagement_in_the_form_is_rejected(client, admin, team, db_session):
    body = payload()
    body["engagements"] = [engagement(team), engagement(team)]

    response = await client.post(CLIENTS_URL, json=body, headers=admin)

    assert response.status_code == 422
    assert "repeated" in str(response.json()["details"])


async def test_invalid_engagement_saves_nothing(client, admin, team, db_session):
    body = payload()
    body["engagements"] = [engagement(team, due_date=None)]

    response = await client.post(CLIENTS_URL, json=body, headers=admin)

    assert response.status_code == 422
    assert await count(db_session, Company) == 0
    assert await count(db_session) == 0


async def test_unknown_company_is_not_found(client, admin, team):
    response = await client.post(
        f"/api/v1/companies/{uuid4()}/engagements", json=engagement(team), headers=admin
    )
    assert response.status_code == 404


async def test_requires_clientes_crear(client, staff, team):
    asociado = await staff("asociado@jhrwise.com", SystemRole.ASOCIADO)
    response = await client.post(
        f"/api/v1/companies/{uuid4()}/engagements", json=engagement(team), headers=asociado
    )
    assert response.status_code == 403


# ── Consultar un compromiso: GET /engagements/{id} ──


async def create_engagement(client, admin, team) -> dict:
    """Crea un cliente con un compromiso de Elaboración de exógena y devuelve el compromiso."""
    body = payload()
    body["engagements"] = [engagement(team)]
    response = await client.post(CLIENTS_URL, json=body, headers=admin)
    assert response.status_code == 201, response.text
    return response.json()["data"]["engagements"][0]


async def test_get_engagement(client, admin, team):
    created = await create_engagement(client, admin, team)

    response = await client.get(f"/api/v1/engagements/{created['id']}", headers=admin)

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "id": created["id"],
        "company_id": created["company_id"],
        "fiscal_year": 2025,
        "status": "por_iniciar",
        "obligation": created["obligation"],
        "service_type": created["service_type"],
    }
    assert response.json()["data"]["obligation"]["name"] == "Información exógena"
    assert response.json()["data"]["service_type"]["name"] == "Elaboración"


async def test_partner_sees_only_his_engagements(client, admin, team, platform, firm):
    created = await create_engagement(client, admin, team)
    url = f"/api/v1/engagements/{created['id']}"
    otro_socio = await platform.user("otro.socio@jhrwise.com", "Otro Socio")
    await platform.member(otro_socio, firm, SystemRole.SOCIO)

    assert (await client.get(url, headers=auth_headers(team.socio, firm))).status_code == 200
    # Fuera de su alcance: 404, como si no existiera
    assert (await client.get(url, headers=auth_headers(otro_socio, firm))).status_code == 404


async def test_engagement_of_another_organization_is_not_found(client, admin, team, platform):
    created = await create_engagement(client, admin, team)
    otra = await platform.tenant("otra-firma")
    otro_admin = await platform.user("admin@otra.co")
    await platform.member(otro_admin, otra, SystemRole.ADMINISTRADOR)

    response = await client.get(
        f"/api/v1/engagements/{created['id']}", headers=auth_headers(otro_admin, otra)
    )

    assert response.status_code == 404


async def test_get_engagement_unknown_or_unauthorized(client, admin, team, platform, firm):
    created = await create_engagement(client, admin, team)
    url = f"/api/v1/engagements/{created['id']}"

    assert (await client.get(f"/api/v1/engagements/{uuid4()}", headers=admin)).status_code == 404
    assert (await client.get(url)).status_code == 401
    outsider = auth_headers(await platform.user("externo@x.co"), firm)
    assert (await client.get(url, headers=outsider)).status_code == 403


# ── Selectores de socio y gerente ──


async def test_members_by_role(client, admin, team, platform, firm):
    ex_socio = await platform.user("ex.socio@jhrwise.com", "Ex Socio")
    await platform.member(ex_socio, firm, SystemRole.SOCIO, MembershipStatus.REVOKED)
    otra = await platform.tenant("otra-firma")
    await platform.member(await platform.user("otro@x.co", "Otro"), otra, SystemRole.SOCIO)

    socios = await client.get("/api/v1/members", params={"role": "socio"}, headers=admin)
    gerentes = await client.get("/api/v1/members", params={"role": "gerente"}, headers=admin)

    assert socios.status_code == 200, socios.text
    assert [m["full_name"] for m in socios.json()["data"]] == ["Juan Restrepo"]
    assert [m["full_name"] for m in gerentes.json()["data"]] == ["María Gómez"]
    invalid = await client.get("/api/v1/members", params={"role": "jefe"}, headers=admin)
    assert invalid.status_code == 422
