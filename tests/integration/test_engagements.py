"""Compromisos: se crean en el paso 3 de "Nuevo cliente" (POST /clients) o después
(POST /companies/{id}/engagements), con socio y gerente de la firma. Hoy todos son de
exógena (tarea A1): no se elige un servicio del catálogo."""

from dataclasses import dataclass
from datetime import UTC
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.modules.clients.models import Company
from app.modules.engagements.models import Engagement
from app.modules.platform.models import MembershipStatus, SystemRole
from tests.integration.conftest import auth_headers
from tests.integration.test_create_client import URL as CLIENTS_URL
from tests.integration.test_create_client import payload


@dataclass
class Firm:
    """El equipo de la firma, listo para crear compromisos."""

    socio: UUID
    gerente: UUID


@pytest.fixture
async def team(platform, firm) -> Firm:
    socio = await platform.user("juan.restrepo@jhrwise.com", "Juan Restrepo")
    await platform.member(socio, firm, SystemRole.SOCIO)
    gerente = await platform.user("maria.gomez@jhrwise.com", "María Gómez")
    await platform.member(gerente, firm, SystemRole.GERENTE)
    return Firm(socio=socio, gerente=gerente)


def engagement(team: Firm, **changes) -> dict:
    data = {
        "fiscal_year": 2025,
        "due_date": "2026-05-15T23:59:00-05:00",
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
        engagement(team, fiscal_year=2026, start_date="2027-01-10T08:00:00-05:00"),
    ]

    response = await client.post(CLIENTS_URL, json=body, headers=admin)

    assert response.status_code == 201, response.text
    created = response.json()["data"]["engagements"]
    assert [
        (
            e["service_type"],
            e["fiscal_year"],
            e["start_date"] is not None,
            e["status"],
            e["partner"]["full_name"],
            e["manager"]["full_name"],
        )
        for e in created
    ] == [
        ("exogena", 2025, False, "created", "Juan Restrepo", "María Gómez"),
        ("exogena", 2026, True, "created", "Juan Restrepo", "María Gómez"),
    ]
    assert await count(db_session) == 2


async def test_dates_keep_date_and_time(client, admin, team, db_session):
    company_id = (await create_client(client, admin))["company"]["id"]

    response = await client.post(
        f"/api/v1/companies/{company_id}/engagements", json=engagement(team), headers=admin
    )

    assert response.status_code == 201, response.text
    saved = await db_session.scalar(select(Engagement))
    # 23:59 en Colombia (-05:00) es 04:59 del día siguiente en UTC: es el mismo instante
    assert saved.due_date.astimezone(UTC).isoformat() == "2026-05-16T04:59:00+00:00"


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
    assert response.json()["data"]["service_type"] == "exogena"
    assert response.json()["data"]["status"] == "created"


async def test_old_service_id_from_the_front_is_ignored(client, admin, team, db_session):
    """El front viejo todavía manda service_id: no debe fallar."""
    company_id = (await create_client(client, admin))["company"]["id"]

    response = await client.post(
        f"/api/v1/companies/{company_id}/engagements",
        json=engagement(team, service_id=uuid4()),
        headers=admin,
    )

    assert response.status_code == 201, response.text
    assert (await db_session.scalar(select(Engagement))).service_id is None


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({"due_date": None}, "due_date"),
        ({"due_date": "2026-05-15"}, "due_date"),  # sin hora ni zona horaria
        ({"due_date": "2026-05-15T23:59:00"}, "due_date"),  # sin zona horaria
        ({"start_date": "2026-01-10"}, "start_date"),
    ],
    ids=["sin-vencimiento", "vencimiento-sin-hora", "vencimiento-sin-zona", "inicio-sin-hora"],
)
async def test_dates_are_validated(client, admin, team, db_session, changes, expected):
    company_id = (await create_client(client, admin))["company"]["id"]
    url = f"/api/v1/companies/{company_id}/engagements"

    response = await client.post(url, json=engagement(team, **changes), headers=admin)

    assert response.status_code == 422
    assert expected in str(response.json()["details"])
    assert await count(db_session) == 0


@pytest.mark.parametrize(
    "changes, field",
    [
        ({"partner_user_id": "gerente"}, "partner_user_id"),  # un gerente como socio
        ({"manager_user_id": "socio"}, "manager_user_id"),  # un socio como gerente
        ({"partner_user_id": "nadie"}, "partner_user_id"),
    ],
    ids=["socio-sin-rol", "gerente-sin-rol", "socio-inexistente"],
)
async def test_team_is_validated(client, admin, team, changes, field):
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


async def test_same_service_type_and_year_is_not_repeated(client, admin, team):
    company_id = (await create_client(client, admin))["company"]["id"]
    url = f"/api/v1/companies/{company_id}/engagements"

    assert (await client.post(url, json=engagement(team), headers=admin)).status_code == 201
    again = await client.post(url, json=engagement(team), headers=admin)
    assert again.status_code == 409

    # Otro año gravable sí
    other_year = engagement(team, fiscal_year=2026, due_date="2027-05-15T23:59:00-05:00")
    assert (await client.post(url, json=other_year, headers=admin)).status_code == 201


async def test_repeated_engagement_in_the_form_is_rejected(client, admin, team, db_session):
    body = payload()
    body["engagements"] = [engagement(team), engagement(team)]

    response = await client.post(CLIENTS_URL, json=body, headers=admin)

    assert response.status_code == 422
    assert "repeated" in str(response.json()["details"])


async def test_invalid_engagement_saves_nothing(client, admin, team, db_session):
    body = payload()
    body["engagements"] = [engagement(team, partner_user_id=uuid4())]

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
        "service_type": "exogena",
        "fiscal_year": 2025,
        "status": "created",
    }


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
