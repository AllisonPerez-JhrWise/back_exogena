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
from tests.integration.conftest import auth_headers
from tests.integration.identity import MembershipStatus, SystemRole
from tests.integration.test_create_client import OTHER_COMPANY_RUT, payload
from tests.integration.test_create_client import URL as CLIENTS_URL


@dataclass
class Firm:
    """El equipo de la firma, listo para crear compromisos."""

    socio: UUID
    gerente: UUID


@pytest.fixture
def team(platform, firm) -> Firm:
    socio = platform.user("juan.restrepo@jhrwise.com", "Juan Restrepo")
    platform.member(socio, firm, SystemRole.SOCIO)
    gerente = platform.user("maria.gomez@jhrwise.com", "María Gómez")
    platform.member(gerente, firm, SystemRole.GERENTE)
    return Firm(socio=socio, gerente=gerente)


def engagement(team: Firm, **changes) -> dict:
    data = {
        "fiscal_year": 2025,
        "due_date": "2026-05-15T23:59:00-05:00",
        "partner_user_id": str(team.socio),
        "manager_user_id": str(team.gerente),
    }
    return {**data, **{k: str(v) if isinstance(v, UUID) else v for k, v in changes.items()}}


def count(session, model=Engagement) -> int:
    return session.scalar(select(func.count()).select_from(model))


def create_client(client, admin, **changes) -> dict:
    response = client.post(CLIENTS_URL, json=payload(**changes), headers=admin)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_client_is_created_with_its_engagements(client, admin, team, db_session):
    body = payload()
    body["engagements"] = [
        engagement(team),
        engagement(team, fiscal_year=2026, start_date="2027-01-10T08:00:00-05:00"),
    ]

    response = client.post(CLIENTS_URL, json=body, headers=admin)

    assert response.status_code == 201, response.text
    created = response.json()["data"]["engagements"]
    assert [
        (
            e["service_type"],
            e["fiscal_year"],
            e["start_date"] is not None,
            e["status"],
            e["partner"]["user_id"],
            e["manager"]["user_id"],
        )
        for e in created
    ] == [
        ("exogena", 2025, False, "created", str(team.socio), str(team.gerente)),
        ("exogena", 2026, True, "created", str(team.socio), str(team.gerente)),
    ]
    assert count(db_session) == 2


def test_dates_keep_date_and_time(client, admin, team, db_session):
    company_id = (create_client(client, admin))["company"]["id"]

    response = client.post(
        f"/api/v1/companies/{company_id}/engagements", json=engagement(team), headers=admin
    )

    assert response.status_code == 201, response.text
    saved = db_session.scalar(select(Engagement))
    # 23:59 en Colombia (-05:00) es 04:59 del día siguiente en UTC: es el mismo instante
    assert saved.due_date.astimezone(UTC).isoformat() == "2026-05-16T04:59:00+00:00"


def test_engagements_step_is_optional(client, admin, db_session):
    data = create_client(client, admin)
    assert data["engagements"] == []
    assert count(db_session) == 0


def test_engagement_is_added_to_an_existing_company(client, admin, team):
    company_id = (create_client(client, admin))["company"]["id"]

    response = client.post(
        f"/api/v1/companies/{company_id}/engagements", json=engagement(team), headers=admin
    )

    assert response.status_code == 201, response.text
    assert response.json()["data"]["company_id"] == company_id
    assert response.json()["data"]["service_type"] == "exogena"
    assert response.json()["data"]["status"] == "created"


def test_old_service_id_from_the_front_is_ignored(client, admin, team, db_session):
    """El front viejo todavía manda service_id: no debe fallar."""
    company_id = (create_client(client, admin))["company"]["id"]

    response = client.post(
        f"/api/v1/companies/{company_id}/engagements",
        json=engagement(team, service_id=uuid4()),
        headers=admin,
    )

    assert response.status_code == 201, response.text
    assert (db_session.scalar(select(Engagement))).service_id is None


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
def test_dates_are_validated(client, admin, team, db_session, changes, expected):
    company_id = (create_client(client, admin))["company"]["id"]
    url = f"/api/v1/companies/{company_id}/engagements"

    response = client.post(url, json=engagement(team, **changes), headers=admin)

    assert response.status_code == 422
    assert expected in str(response.json()["details"])
    assert count(db_session) == 0


# Que socio y gerente sean personas de la firma lo valida Identidad al registrarlos en el
# equipo del compromiso (segmento 3b), no este servicio.


def test_same_service_type_and_year_is_not_repeated(client, admin, team):
    company_id = (create_client(client, admin))["company"]["id"]
    url = f"/api/v1/companies/{company_id}/engagements"

    assert (client.post(url, json=engagement(team), headers=admin)).status_code == 201
    again = client.post(url, json=engagement(team), headers=admin)
    assert again.status_code == 409

    # Otro año gravable sí
    other_year = engagement(team, fiscal_year=2026, due_date="2027-05-15T23:59:00-05:00")
    assert (client.post(url, json=other_year, headers=admin)).status_code == 201


def test_repeated_engagement_in_the_form_is_rejected(client, admin, team, db_session):
    body = payload()
    body["engagements"] = [engagement(team), engagement(team)]

    response = client.post(CLIENTS_URL, json=body, headers=admin)

    assert response.status_code == 422
    assert "repeated" in str(response.json()["details"])


def test_invalid_engagement_saves_nothing(client, admin, team, db_session):
    body = payload()
    body["engagements"] = [engagement(team, due_date="2026-05-15")]  # sin hora

    response = client.post(CLIENTS_URL, json=body, headers=admin)

    assert response.status_code == 422
    assert count(db_session, Company) == 0
    assert count(db_session) == 0


def test_unknown_company_is_not_found(client, admin, team):
    response = client.post(
        f"/api/v1/companies/{uuid4()}/engagements", json=engagement(team), headers=admin
    )
    assert response.status_code == 404


def test_requires_clientes_crear(client, staff, team):
    asociado = staff("asociado@jhrwise.com", SystemRole.ASOCIADO)
    response = client.post(
        f"/api/v1/companies/{uuid4()}/engagements", json=engagement(team), headers=asociado
    )
    assert response.status_code == 403


# ── Consultar un compromiso: GET /engagements/{id} ──


def create_engagement(client, admin, team) -> dict:
    """Crea un cliente con un compromiso de Elaboración de exógena y devuelve el compromiso."""
    body = payload()
    body["engagements"] = [engagement(team)]
    response = client.post(CLIENTS_URL, json=body, headers=admin)
    assert response.status_code == 201, response.text
    return response.json()["data"]["engagements"][0]


def test_get_engagement(client, admin, team):
    created = create_engagement(client, admin, team)

    response = client.get(f"/api/v1/engagements/{created['id']}", headers=admin)

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "id": created["id"],
        "company_id": created["company_id"],
        "service_type": "exogena",
        "fiscal_year": 2025,
        "status": "created",
    }


def test_partner_sees_only_his_engagements(client, admin, team, platform, firm):
    created = create_engagement(client, admin, team)
    url = f"/api/v1/engagements/{created['id']}"
    # Otro socio, con un compromiso en otra empresa
    otro_socio = platform.user("otro.socio@jhrwise.com", "Otro Socio")
    platform.member(otro_socio, firm, SystemRole.SOCIO)
    body = payload(rut=OTHER_COMPANY_RUT)
    body["engagements"] = [engagement(team, partner_user_id=otro_socio)]
    assert client.post(CLIENTS_URL, json=body, headers=admin).status_code == 201
    # Y uno sin ningún compromiso
    sin_compromisos = platform.user("nuevo.socio@jhrwise.com", "Nuevo Socio")
    platform.member(sin_compromisos, firm, SystemRole.SOCIO)

    assert (client.get(url, headers=auth_headers(team.socio, firm))).status_code == 200
    # Fuera de su alcance: 404, como si no existiera
    assert (client.get(url, headers=auth_headers(otro_socio, firm))).status_code == 404
    # Sin compromisos no tiene el permiso en ninguna parte: 403
    assert (client.get(url, headers=auth_headers(sin_compromisos, firm))).status_code == 403


def test_engagement_of_another_organization_is_not_found(client, admin, team, platform):
    created = create_engagement(client, admin, team)
    otra = platform.tenant("otra-firma")
    otro_admin = platform.user("admin@otra.co")
    platform.member(otro_admin, otra, SystemRole.ADMINISTRADOR)

    response = client.get(
        f"/api/v1/engagements/{created['id']}", headers=auth_headers(otro_admin, otra)
    )

    assert response.status_code == 404


def test_get_engagement_unknown_or_unauthorized(client, admin, team, platform, firm):
    created = create_engagement(client, admin, team)
    url = f"/api/v1/engagements/{created['id']}"

    assert (client.get(f"/api/v1/engagements/{uuid4()}", headers=admin)).status_code == 404
    assert (client.get(url)).status_code == 401
    outsider = auth_headers(platform.user("externo@x.co"), firm)
    assert (client.get(url, headers=outsider)).status_code == 403


# ── El equipo se registra en Identidad (PUT /compromisos/{id}/equipo/{user_id}) ──


def test_team_is_registered_in_identity(client, admin, team, platform, firm):
    created = create_engagement(client, admin, team)
    engagement_id, company_id = UUID(created["id"]), UUID(created["company_id"])

    assert platform.team[(engagement_id, team.socio)] == (firm, company_id, ["socio"])
    assert platform.team[(engagement_id, team.gerente)] == (firm, company_id, ["gerente"])


def test_same_person_as_partner_and_manager_goes_once(client, admin, team, platform, firm):
    body = payload()
    body["engagements"] = [engagement(team, manager_user_id=team.socio)]
    response = client.post(CLIENTS_URL, json=body, headers=admin)

    assert response.status_code == 201, response.text
    engagement_id = UUID(response.json()["data"]["engagements"][0]["id"])
    assert [roles for (e, _), (_, _, roles) in platform.team.items() if e == engagement_id] == [
        ["socio", "gerente"]
    ]


@pytest.mark.parametrize("field", ["partner_user_id", "manager_user_id"])
def test_person_outside_the_firm_is_rejected_and_nothing_is_saved(
    client, admin, team, platform, db_session, field
):
    """Identidad responde 404 (no es miembro): 422 con el campo, y no queda nada."""
    outsider = platform.user("externo@x.co")
    body = payload()
    body["engagements"] = [engagement(team, **{field: outsider})]

    response = client.post(CLIENTS_URL, json=body, headers=admin)

    assert response.status_code == 422
    assert response.json()["details"] == {
        "engagement": 0,
        "field": field,
        "cause": "not_a_member",
    }
    assert count(db_session, Company) == 0
    assert count(db_session) == 0


def test_revoked_partner_is_rejected(client, admin, team, platform, firm):
    ex_socio = platform.user("ex.socio@jhrwise.com")
    platform.member(ex_socio, firm, SystemRole.SOCIO, MembershipStatus.REVOKED)
    company_id = create_client(client, admin)["company"]["id"]

    response = client.post(
        f"/api/v1/companies/{company_id}/engagements",
        json=engagement(team, partner_user_id=ex_socio),
        headers=admin,
    )
    assert response.status_code == 422
    assert response.json()["details"]["field"] == "partner_user_id"


def test_identity_down_saves_nothing(client, admin, team, platform, db_session):
    """Si Identidad no responde: 503, el usuario vuelve a intentar, y no queda nada."""
    platform.unavailable = True
    body = payload()
    body["engagements"] = [engagement(team)]

    response = client.post(CLIENTS_URL, json=body, headers=admin)

    assert response.status_code == 503
    assert response.json()["code"] == "service_unavailable"
    assert count(db_session, Company) == 0
    assert count(db_session) == 0
