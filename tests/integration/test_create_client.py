"""POST /api/v1/clients: el asistente "Nuevo cliente" de punta a punta, sobre la
plataforma (tenants, users, memberships) con su seguridad por filas."""

import copy
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text

from app.core.exceptions import BusinessRuleError
from app.modules.clients.models import (
    Client,
    ClientMember,
    Company,
    CompanyRutVersion,
    CompanyTaxResponsibility,
)
from app.modules.clients.nit import calculate_dv
from app.modules.clients.service import ClientService
from app.modules.platform.models import MembershipStatus, SystemRole, Tenant, TenantKind, User
from tests.integration.conftest import auth_headers

URL = "/api/v1/clients"
GENERATED = (date.today() - timedelta(days=5)).isoformat()

# El ejemplo del mockup (con el DV correcto: 900123456 -> 8)
PAYLOAD = {
    "rut": {
        "nit": "900123456",
        "dv": "8",
        "person_type": "juridica",
        "taxpayer_type": "Persona jurídica",
        "legal_name": "Comercializadora Andina SAS",
        "address": "Calle 100 # 15-20, oficina 402",
        "department_code": "11",
        "city_code": "11001",
        "rut_email": "contabilidad@andina.com.co",
        "main_activity_code": "4719",
        "tax_responsibilities": ["05", "48", "42"],
        "rut_status": "activo",
        "generated_at": GENERATED,
        "rut_updated_at": "2026-09-12",
    },
    "organization": {
        "trade_name": "Andina Comercial",
        "contact_name": "Paula Córdoba",
        "contact_email": "paula.cordoba@andina.com.co",
        "contact_phone": "+57 310 555 4321",
        "notes": "Prefiere reuniones los martes.",
    },
    "users": [
        {
            "email": "paula.cordoba@andina.com.co",
            "first_name": "Paula",
            "last_name": "Córdoba",
            "phone": "+57 310 555 4321",
            "position": "Contadora",
        },
        {
            "email": "carlos.mejia@revisoria.com.co",
            "first_name": "Carlos",
            "last_name": "Mejía",
            "phone": "+57 315 222 1098",
            "position": "Revisor fiscal",
        },
    ],
}

# Segunda empresa del mismo grupo (DV correcto: 800197268 -> 4)
OTHER_COMPANY_RUT = {"nit": "800197268", "dv": "4", "legal_name": "Andina Zona Franca SAS"}


def payload(**changes) -> dict:
    """Copia del ejemplo con cambios: payload(rut={"dv": "1"}) cambia solo el DV."""
    data = copy.deepcopy(PAYLOAD)
    for section, values in changes.items():
        if isinstance(values, dict) and isinstance(data.get(section), dict):
            data[section].update(values)
        else:
            data[section] = values
    return data


async def count(session, model, *conditions) -> int:
    return await session.scalar(select(func.count()).select_from(model).where(*conditions))


async def role_of(session, user_id: UUID, tenant_id: UUID) -> tuple[str, str]:
    """(rol, estado) de la membresía de la persona en el tenant."""
    row = (
        await session.execute(
            text(
                "SELECT r.code, m.status FROM public.memberships m "
                "JOIN public.membership_roles mr ON mr.membership_id = m.id "
                "JOIN public.roles r ON r.id = mr.role_id "
                "WHERE m.user_id = :user_id AND m.tenant_id = :tenant_id"
            ),
            {"user_id": user_id, "tenant_id": tenant_id},
        )
    ).one()
    return row.code, row.status


async def test_new_client_with_company_and_users(client, admin, db_session):
    response = await client.post(URL, json=PAYLOAD, headers=admin)

    assert response.status_code == 201, response.text
    data = response.json()["data"]

    # El cliente toma el nombre y el contacto de su primera empresa
    assert data["client"]["name"] == "Comercializadora Andina SAS"
    assert data["client"]["contact_name"] == "Paula Córdoba"
    assert data["client"]["notes"] == "Prefiere reuniones los martes."

    company = data["company"]
    assert company["client_id"] == data["client"]["id"]
    assert company["display_name"] == "Comercializadora Andina SAS"
    assert company["trade_name"] == "Andina Comercial"
    assert company["contact_email"] == "paula.cordoba@andina.com.co"
    assert company["tax_responsibilities"] == ["05", "48", "42"]
    assert (company["rut_generated_at"], company["rut_updated_at"]) == (GENERATED, "2026-09-12")

    # La cuenta del cliente en la plataforma
    tenant = await db_session.get(Tenant, UUID(data["client"]["tenant_id"]))
    assert (tenant.kind, tenant.name) == (TenantKind.CLIENT, "Comercializadora Andina SAS")

    # Primera versión del RUT, con sus dos fechas y el año gravable que cubre
    version = (await db_session.execute(select(CompanyRutVersion))).scalar_one()
    assert (version.generated_at.isoformat(), version.covers_tax_year) == (GENERATED, 2026)
    assert version.is_historical is False

    # Usuarios: invitados, rol cliente, sin Cognito todavía
    assert [(u["full_name"], u["role"], u["position"]) for u in data["users"]] == [
        ("Paula Córdoba", "cliente", "Contadora"),
        ("Carlos Mejía", "cliente", "Revisor fiscal"),
    ]
    paula = UUID(data["users"][0]["user_id"])
    assert (await db_session.get(User, paula)).cognito_sub is None
    assert await role_of(db_session, paula, tenant.id) == ("cliente", "invited")
    assert await count(db_session, ClientMember) == 2


async def test_steps_3_and_4_are_optional(client, admin, db_session):
    body = payload(users=[])
    del body["organization"]

    response = await client.post(URL, json=body, headers=admin)

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert (data["users"], data["engagements"]) == ([], [])
    assert data["company"]["trade_name"] is None
    assert await count(db_session, Tenant, Tenant.kind == TenantKind.CLIENT) == 1


async def test_company_is_added_to_an_existing_client(client, admin, db_session):
    first = (await client.post(URL, json=PAYLOAD, headers=admin)).json()["data"]
    client_id = first["client"]["id"]

    body = payload(
        client_id=client_id,
        rut=OTHER_COMPANY_RUT,
        organization={"contact_name": "Otra persona", "notes": None},
        users=[{**PAYLOAD["users"][1], "position": "Revisor fiscal suplente"}],
    )
    response = await client.post(URL, json=body, headers=admin)

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["client"]["id"] == client_id
    assert data["company"]["client_id"] == client_id
    # Los datos de contacto son por empresa: el cliente conserva los suyos
    assert data["company"]["contact_name"] == "Otra persona"
    assert data["client"]["contact_name"] == "Paula Córdoba"
    # Una sola cuenta y un solo registro por persona; el cargo se actualiza
    assert await count(db_session, Tenant, Tenant.kind == TenantKind.CLIENT) == 1
    assert await count(db_session, Company, Company.client_id == UUID(client_id)) == 2
    assert await count(db_session, ClientMember) == 2
    assert data["users"][0]["user_id"] == first["users"][1]["user_id"]
    assert data["users"][0]["position"] == "Revisor fiscal suplente"


async def test_existing_client_of_another_organization_is_not_found(
    client, admin, db_session, platform
):
    other_firm = await platform.tenant("otra-firma")
    other_admin = await platform.user("admin@otra.co")
    await platform.member(other_admin, other_firm, SystemRole.ADMINISTRADOR)
    foreign = (
        await client.post(URL, json=PAYLOAD, headers=auth_headers(other_admin, other_firm))
    ).json()["data"]["client"]["id"]

    response = await client.post(
        URL, json=payload(client_id=foreign, rut=OTHER_COMPANY_RUT), headers=admin
    )
    assert response.status_code == 404


async def test_requires_clientes_crear_in_the_organization(client, staff, platform):
    assert (await client.post(URL, json=PAYLOAD)).status_code == 401

    admin = await staff("admin@jhrwise.com", SystemRole.ADMINISTRADOR)
    no_tenant = {"Authorization": admin["Authorization"]}
    assert (await client.post(URL, json=PAYLOAD, headers=no_tenant)).status_code == 400

    # Un asociado puede consultar clientes, pero no crearlos
    asociado = await staff("asociado@jhrwise.com", SystemRole.ASOCIADO)
    response = await client.post(URL, json=PAYLOAD, headers=asociado)
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"

    revoked = await staff("ex@jhrwise.com", SystemRole.ADMINISTRADOR, MembershipStatus.REVOKED)
    assert (await client.post(URL, json=PAYLOAD, headers=revoked)).status_code == 403

    other = await platform.tenant("otra-firma")
    headers = {**admin, "X-Tenant-Id": str(other)}
    assert (await client.post(URL, json=PAYLOAD, headers=headers)).status_code == 403


async def test_nit_is_unique_in_the_organization(client, admin, db_session, platform):
    first = await client.post(URL, json=PAYLOAD, headers=admin)
    company_id = first.json()["data"]["company"]["id"]

    again = await client.post(URL, json=payload(users=[]), headers=admin)
    assert again.status_code == 409
    assert again.json()["details"] == {"cause": "nit_exists", "company_id": company_id}

    # Otra firma sí puede tener el mismo NIT como cliente suyo
    other_firm = await platform.tenant("otra-firma")
    other_admin = await platform.user("admin@otra.co")
    await platform.member(other_admin, other_firm, SystemRole.ADMINISTRADOR)
    response = await client.post(
        URL, json=payload(users=[]), headers=auth_headers(other_admin, other_firm)
    )
    assert response.status_code == 201, response.text


@pytest.mark.parametrize(
    "rut, cause",
    [
        ({"rut_status": "cancelado"}, "rut_not_active"),
        ({"rut_status": "suspendido"}, "rut_not_active"),
        ({"generated_at": (date.today() - timedelta(days=31)).isoformat()}, "rut_too_old"),
        (
            {"generated_at": (date.today() + timedelta(days=1)).isoformat()},
            "rut_generated_in_future",
        ),
    ],
    ids=["cancelado", "suspendido", "mas-de-30-dias", "fecha-futura"],
)
async def test_rut_rules_block_the_creation(client, admin, db_session, rut, cause):
    response = await client.post(URL, json=payload(rut=rut), headers=admin)

    assert response.status_code == 422
    assert response.json()["details"]["cause"] == cause
    assert await count(db_session, Company) == 0
    assert await count(db_session, Tenant, Tenant.kind == TenantKind.CLIENT) == 0


async def test_rut_of_exactly_30_days_is_accepted(client, admin):
    thirty = (date.today() - timedelta(days=30)).isoformat()
    response = await client.post(URL, json=payload(rut={"generated_at": thirty}), headers=admin)
    assert response.status_code == 201, response.text


async def test_rut_too_old_tells_how_many_days(client, admin):
    old = (date.today() - timedelta(days=45)).isoformat()
    response = await client.post(URL, json=payload(rut={"generated_at": old}), headers=admin)
    assert response.json()["details"] == {"cause": "rut_too_old", "days": 45, "max_days": 30}


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({"rut": {"dv": "1"}}, "verification digit"),
        ({"rut": {"legal_name": None}}, "legal_name is required"),
        (
            {"rut": {"person_type": "natural", "legal_name": None, "first_name": "Juan"}},
            "last_name are required",
        ),
        ({"rut": {"city_code": "05001"}}, "does not belong"),
        ({"rut": {"tax_responsibilities": ["05", "05"]}}, "repeated codes"),
        ({"rut": {"generated_at": None}}, "generated_at"),
        ({"users": [PAYLOAD["users"][0], PAYLOAD["users"][0]]}, "repeated emails"),
        ({"organization": {"notes": "x" * 2001}}, "notes"),
    ],
    ids=[
        "dv",
        "juridica-sin-razon-social",
        "natural-sin-apellido",
        "municipio-otro-depto",
        "responsabilidad-repetida",
        "sin-fecha-de-generacion",
        "correo-repetido",
        "notas-muy-largas",
    ],
)
async def test_invalid_payload_is_rejected(client, admin, db_session, changes, expected):
    response = await client.post(URL, json=payload(**changes), headers=admin)

    assert response.status_code == 422
    assert expected in str(response.json()["details"])
    assert await count(db_session, Company) == 0


async def test_natural_person_client(client, admin):
    natural = payload(
        rut={
            "nit": "1020304050",
            "dv": calculate_dv("1020304050"),
            "person_type": "natural",
            "legal_name": None,
            "first_name": "Juan",
            "middle_name": "Pablo",
            "last_name": "Restrepo",
        }
    )
    response = await client.post(URL, json=natural, headers=admin)

    assert response.status_code == 201, response.text
    assert response.json()["data"]["company"]["display_name"] == "Juan Pablo Restrepo"
    assert response.json()["data"]["client"]["name"] == "Juan Pablo Restrepo"


async def test_nothing_is_saved_if_something_fails(client, admin, db_session, monkeypatch):
    """Si falla a mitad de camino (aquí, al crear el 2.º usuario), no queda nada guardado."""
    original = ClientService._get_or_create_user
    calls = {"n": 0}

    async def fail_on_second_user(self, item):
        calls["n"] += 1
        if calls["n"] == 2:
            raise BusinessRuleError("Simulated failure")
        return await original(self, item)

    monkeypatch.setattr(ClientService, "_get_or_create_user", fail_on_second_user)
    response = await client.post(URL, json=PAYLOAD, headers=admin)

    assert response.status_code == 422
    for model in (Client, Company, CompanyTaxResponsibility, CompanyRutVersion, ClientMember):
        assert await count(db_session, model) == 0
    assert await count(db_session, Tenant, Tenant.kind == TenantKind.CLIENT) == 0
    assert await count(db_session, User, User.email == "paula.cordoba@andina.com.co") == 0


async def test_person_from_another_client_is_not_linked_yet(client, admin, db_session, platform):
    """La seguridad por filas no deja ver a una persona de otro tenant. Hasta que la
    plataforma tenga una función para buscarla por email, se rechaza sin guardar nada."""
    other_client = await platform.tenant("cliente-otro", TenantKind.CLIENT)
    carlos = await platform.user("carlos.mejia@revisoria.com.co", "Carlos Mejía")
    await platform.member(carlos, other_client, SystemRole.CLIENTE)

    response = await client.post(URL, json=PAYLOAD, headers=admin)

    assert response.status_code == 409
    assert response.json()["details"] == {"email": "carlos.mejia@revisoria.com.co"}
    assert await count(db_session, Company) == 0


async def test_client_account_is_visible_only_inside_it(client, admin, db_session):
    """Seguridad por filas: como wiseerp_app, la cuenta nueva solo se ve declarándola."""
    tenant_id = (await client.post(URL, json=PAYLOAD, headers=admin)).json()["data"]["client"][
        "tenant_id"
    ]
    await db_session.execute(text("SET ROLE wiseerp_app"))
    try:
        for tenant_context, expected in (("", 0), (tenant_id, 1)):
            await db_session.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_context}
            )
            await db_session.execute(text("SELECT set_config('app.user_id', '', true)"))
            visible = await db_session.scalar(
                text("SELECT count(*) FROM public.tenants WHERE id = :id"), {"id": tenant_id}
            )
            assert visible == expected
    finally:
        await db_session.execute(text("RESET ROLE"))


# ── Paso 1: NIT existente y buscador de clientes ──


async def test_nit_check(client, admin):
    url = "/api/v1/companies/nit-check"
    missing = (await client.get(url, params={"nit": "900123456"}, headers=admin)).json()["data"]
    assert missing == {"exists": False, "company_id": None, "client_id": None, "display_name": None}

    created = (await client.post(URL, json=PAYLOAD, headers=admin)).json()["data"]
    check = (await client.get(url, params={"nit": "900123456"}, headers=admin)).json()["data"]
    assert check == {
        "exists": True,
        "company_id": created["company"]["id"],
        "client_id": created["client"]["id"],
        "display_name": "Comercializadora Andina SAS",
    }
    assert (await client.get(url, params={"nit": "90-1"}, headers=admin)).status_code == 422


async def test_search_clients(client, admin):
    created = (await client.post(URL, json=PAYLOAD, headers=admin)).json()["data"]
    await client.post(
        URL, json=payload(client_id=created["client"]["id"], rut=OTHER_COMPANY_RUT), headers=admin
    )

    for q in ("andina", "ZONA FRANCA", "800197", None):
        response = await client.get("/api/v1/clients/search", params={"q": q}, headers=admin)
        assert response.status_code == 200, response.text
        assert [(c["name"], c["companies"]) for c in response.json()["data"]] == [
            ("Comercializadora Andina SAS", 2)
        ], q
    response = await client.get("/api/v1/clients/search", params={"q": "nada"}, headers=admin)
    assert response.json()["data"] == []


async def test_unknown_existing_client_is_not_found(client, admin):
    response = await client.post(URL, json=payload(client_id=str(uuid4())), headers=admin)
    assert response.status_code == 404
