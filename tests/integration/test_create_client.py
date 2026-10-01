"""POST /api/v1/clients: el asistente "Nuevo cliente" de punta a punta, y el catálogo de
grupos (/groups).

La empresa es el cliente; el grupo es opcional. Todo pasa dentro de la firma (X-Tenant-Id):
los clientes no son tenants de la plataforma."""

import copy
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.core.exceptions import BusinessRuleError
from app.modules.clients.models import (
    Company,
    CompanyRutVersion,
    CompanyTaxResponsibility,
    CompanyUser,
    Group,
)
from app.modules.clients.nit import calculate_dv
from app.modules.clients.service import ClientService
from app.modules.platform.models import MembershipStatus, SystemRole, Tenant, TenantKind
from tests.integration.conftest import auth_headers

URL = "/api/v1/clients"
GROUPS = "/api/v1/groups"
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

# Otra empresa (DV correcto: 800197268 -> 4)
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


async def create(client, headers, **changes) -> dict:
    response = await client.post(URL, json=payload(**changes), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_new_client_without_group(client, admin, db_session):
    response = await client.post(URL, json=PAYLOAD, headers=admin)

    assert response.status_code == 201, response.text
    data = response.json()["data"]

    company = data["company"]
    assert company["group"] is None
    assert company["display_name"] == "Comercializadora Andina SAS"
    assert company["trade_name"] == "Andina Comercial"
    assert company["contact_name"] == "Paula Córdoba"
    assert company["notes"] == "Prefiere reuniones los martes."
    assert company["tax_responsibilities"] == ["05", "48", "42"]
    assert (company["rut_generated_at"], company["rut_updated_at"]) == (GENERATED, "2026-09-12")

    # El cliente es un registro de la firma: no se crea ningún tenant ni ningún grupo
    assert await count(db_session, Tenant, Tenant.kind == TenantKind.CLIENT) == 0
    assert await count(db_session, Group) == 0

    # Primera versión del RUT, con sus dos fechas y el año gravable que cubre
    version = (await db_session.execute(select(CompanyRutVersion))).scalar_one()
    assert (version.generated_at.isoformat(), version.covers_tax_year) == (GENERATED, 2026)
    assert version.is_historical is False

    # Usuarios: asignados a esta empresa, pendientes de invitar con Identidad
    assert [(u["full_name"], u["position"], u["phone"], u["user_id"]) for u in data["users"]] == [
        ("Paula Córdoba", "Contadora", "+57 310 555 4321", None),
        ("Carlos Mejía", "Revisor fiscal", "+57 315 222 1098", None),
    ]
    assert await count(db_session, CompanyUser) == 2


async def test_new_group_is_created_with_the_company(client, admin, db_session):
    data = await create(client, admin, group_name="Grupo Andina")

    assert data["company"]["group"]["name"] == "Grupo Andina"
    group = await db_session.get(Group, UUID(data["company"]["group"]["id"]))
    assert group.name_key == "grupo andina"


async def test_company_joins_an_existing_group(client, admin, db_session):
    first = await create(client, admin, group_name="Grupo Andina")
    group_id = first["company"]["group"]["id"]

    second = await create(
        client,
        admin,
        group_id=group_id,
        rut=OTHER_COMPANY_RUT,
        organization={"contact_name": "Otra persona", "notes": None},
        users=[{**PAYLOAD["users"][1], "position": "Revisor fiscal suplente"}],
    )

    assert second["company"]["group"]["id"] == group_id
    # Los datos de contacto y los usuarios son de cada empresa
    assert second["company"]["contact_name"] == "Otra persona"
    assert await count(db_session, Group) == 1
    assert await count(db_session, Company, Company.group_id == UUID(group_id)) == 2
    carlos = select(CompanyUser.position).where(
        CompanyUser.email == "carlos.mejia@revisoria.com.co"
    )
    assert sorted(await db_session.scalars(carlos)) == ["Revisor fiscal", "Revisor fiscal suplente"]


async def test_same_group_written_differently_is_not_duplicated(client, admin, db_session):
    first = await create(client, admin, group_name="Grupo Andina")

    response = await client.post(
        URL, json=payload(group_name="  GRUPO   ándina ", rut=OTHER_COMPANY_RUT), headers=admin
    )

    assert response.status_code == 409
    assert response.json()["details"] == {
        "cause": "group_exists",
        "group_id": first["company"]["group"]["id"],
        "name": "Grupo Andina",
    }
    assert await count(db_session, Company) == 1  # la segunda empresa no se creó


async def test_group_id_and_group_name_are_exclusive(client, admin):
    body = payload(group_id=str(uuid4()), group_name="Grupo X")
    response = await client.post(URL, json=body, headers=admin)
    assert response.status_code == 422
    assert "not both" in str(response.json()["details"])


async def test_group_of_another_organization_is_not_found(client, admin, platform):
    other_firm = await platform.tenant("otra-firma")
    other_admin = await platform.user("admin@otra.co")
    await platform.member(other_admin, other_firm, SystemRole.ADMINISTRADOR)
    foreign = await create(client, auth_headers(other_admin, other_firm), group_name="Grupo Andina")

    response = await client.post(
        URL,
        json=payload(group_id=foreign["company"]["group"]["id"], rut=OTHER_COMPANY_RUT),
        headers=admin,
    )
    assert response.status_code == 404
    unknown = await client.post(URL, json=payload(group_id=str(uuid4())), headers=admin)
    assert unknown.status_code == 404


async def test_steps_3_and_4_are_optional(client, admin):
    body = payload(users=[])
    del body["organization"]

    response = await client.post(URL, json=body, headers=admin)

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert (data["users"], data["engagements"]) == ([], [])
    assert data["company"]["trade_name"] is None


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


async def test_nit_is_unique_in_the_organization(client, admin, platform):
    company_id = (await create(client, admin))["company"]["id"]

    again = await client.post(URL, json=payload(users=[]), headers=admin)
    assert again.status_code == 409
    assert again.json()["details"] == {"cause": "nit_exists", "company_id": company_id}

    # Otra firma sí puede tener el mismo NIT como cliente suyo
    other_firm = await platform.tenant("otra-firma")
    other_admin = await platform.user("admin@otra.co")
    await platform.member(other_admin, other_firm, SystemRole.ADMINISTRADOR)
    await create(client, auth_headers(other_admin, other_firm), users=[])


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
    response = await client.post(URL, json=payload(rut=rut, group_name="Grupo X"), headers=admin)

    assert response.status_code == 422
    assert response.json()["details"]["cause"] == cause
    assert await count(db_session, Company) == 0
    assert await count(db_session, Group) == 0


async def test_rut_of_exactly_30_days_is_accepted(client, admin):
    thirty = (date.today() - timedelta(days=30)).isoformat()
    await create(client, admin, rut={"generated_at": thirty})


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
        ({"group_name": "   "}, "group_name"),
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
        "grupo-vacio",
    ],
)
async def test_invalid_payload_is_rejected(client, admin, db_session, changes, expected):
    response = await client.post(URL, json=payload(**changes), headers=admin)

    assert response.status_code == 422
    assert expected in str(response.json()["details"])
    assert await count(db_session, Company) == 0


async def test_natural_person_client(client, admin):
    data = await create(
        client,
        admin,
        rut={
            "nit": "1020304050",
            "dv": calculate_dv("1020304050"),
            "person_type": "natural",
            "legal_name": None,
            "first_name": "Juan",
            "middle_name": "Pablo",
            "last_name": "Restrepo",
        },
    )
    assert data["company"]["display_name"] == "Juan Pablo Restrepo"


async def test_nothing_is_saved_if_something_fails(client, admin, db_session, monkeypatch):
    """Si falla a mitad de camino (aquí, al crear el 2.º usuario), no queda nada guardado,
    ni siquiera el grupo nuevo."""
    original = ClientService._add_user
    calls = {"n": 0}

    async def fail_on_second_user(self, company, item, actor):
        calls["n"] += 1
        if calls["n"] == 2:
            raise BusinessRuleError("Simulated failure")
        return await original(self, company, item, actor)

    monkeypatch.setattr(ClientService, "_add_user", fail_on_second_user)
    response = await client.post(URL, json=payload(group_name="Grupo X"), headers=admin)

    assert response.status_code == 422
    for model in (Group, Company, CompanyTaxResponsibility, CompanyRutVersion, CompanyUser):
        assert await count(db_session, model) == 0


# ── Paso 1: NIT existente ──


async def test_nit_check(client, admin):
    url = "/api/v1/companies/nit-check"
    missing = (await client.get(url, params={"nit": "900123456"}, headers=admin)).json()["data"]
    assert missing == {"exists": False, "company_id": None, "group_id": None, "display_name": None}

    created = await create(client, admin, group_name="Grupo Andina")
    check = (await client.get(url, params={"nit": "900123456"}, headers=admin)).json()["data"]
    assert check == {
        "exists": True,
        "company_id": created["company"]["id"],
        "group_id": created["company"]["group"]["id"],
        "display_name": "Comercializadora Andina SAS",
    }
    assert (await client.get(url, params={"nit": "90-1"}, headers=admin)).status_code == 422


# ── Catálogo de grupos ──


async def test_search_groups(client, admin):
    first = await create(client, admin, group_name="Grupo Sacyr")
    await create(client, admin, group_id=first["company"]["group"]["id"], rut=OTHER_COMPANY_RUT)
    await client.post(GROUPS, json={"name": "Grupo Muisca"}, headers=admin)

    async def names(q):
        response = await client.get(GROUPS, params={"q": q}, headers=admin)
        assert response.status_code == 200, response.text
        return [(g["name"], g["companies"]) for g in response.json()["data"]]

    assert await names(None) == [("Grupo Muisca", 0), ("Grupo Sacyr", 2)]
    assert await names("SÁCYR") == [("Grupo Sacyr", 2)]  # sin importar mayúsculas ni tildes
    assert await names("nada") == []


async def test_create_and_rename_group(client, admin):
    created = await client.post(GROUPS, json={"name": "Grupo Sacyr"}, headers=admin)
    assert created.status_code == 201, created.text
    group = created.json()["data"]

    # Repetido, escrito distinto: 409 con el grupo existente
    again = await client.post(GROUPS, json={"name": "grupo  SACYR"}, headers=admin)
    assert again.status_code == 409
    assert again.json()["details"]["group_id"] == group["id"]

    renamed = await client.patch(
        f"{GROUPS}/{group['id']}", json={"name": "Grupo Sacyr Colombia"}, headers=admin
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["data"]["name"] == "Grupo Sacyr Colombia"

    other = (await client.post(GROUPS, json={"name": "Otro"}, headers=admin)).json()["data"]
    clash = await client.patch(
        f"{GROUPS}/{other['id']}", json={"name": "grupo sacyr colombia"}, headers=admin
    )
    assert clash.status_code == 409
    assert (
        await client.patch(f"{GROUPS}/{uuid4()}", json={"name": "X"}, headers=admin)
    ).status_code == 404


async def test_groups_require_clientes_crear(client, staff):
    asociado = await staff("asociado@jhrwise.com", SystemRole.ASOCIADO)
    assert (await client.get(GROUPS, headers=asociado)).status_code == 403
    assert (await client.post(GROUPS, json={"name": "X"}, headers=asociado)).status_code == 403
