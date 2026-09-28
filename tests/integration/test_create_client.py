"""POST /api/v1/clients: el formulario "Nuevo cliente" de punta a punta, sobre la
plataforma (tenants, users, memberships) con su seguridad por filas."""

import copy
from uuid import UUID

import pytest
from sqlalchemy import func, select, text

from app.core.exceptions import BusinessRuleError
from app.modules.clients.models import Client, ClientContact
from app.modules.clients.nit import calculate_dv
from app.modules.clients.service import ClientService
from app.modules.platform.models import (
    Membership,
    MembershipStatus,
    SystemRole,
    Tenant,
    TenantKind,
    User,
)
from tests.integration.conftest import auth_headers

URL = "/api/v1/clients"

# El ejemplo del mockup (con el DV correcto: 900123456 -> 8)
PAYLOAD = {
    "rut": {
        "nit": "900123456",
        "dv": "8",
        "person_type": "juridica",
        "legal_name": "Comercializadora Andina SAS",
        "address": "Calle 100 # 15-20, oficina 402",
        "department_code": "11",
        "city_code": "11001",
        "rut_email": "contabilidad@andina.com.co",
        "main_activity_code": "4719",
        "tax_responsibilities": ["05", "48", "42"],
        "rut_status": "activo",
        "rut_updated_at": "2026-09-12",
    },
    "organization": {"trade_name": "Andina Comercial"},
    "users": [
        {
            "email": "paula.cordoba@andina.com.co",
            "first_name": "Paula",
            "last_name": "Córdoba",
            "phone": "+57 310 555 4321",
            "position": "Contadora",
            "is_primary_contact": True,
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


def payload(**changes) -> dict:
    """Copia del ejemplo con cambios: payload(rut={"dv": "1"}) cambia solo el DV."""
    data = copy.deepcopy(PAYLOAD)
    for section, values in changes.items():
        if isinstance(values, dict):
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


async def test_admin_creates_client_on_the_platform(client, admin, db_session):
    response = await client.post(URL, json=PAYLOAD, headers=admin)

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["display_name"] == "Comercializadora Andina SAS"
    assert data["trade_name"] == "Andina Comercial"
    assert data["tax_responsibilities"] == ["05", "48", "42"]
    assert [
        (u["full_name"], u["role"], u["position"], u["phone"], u["is_primary_contact"])
        for u in data["users"]
    ] == [
        ("Paula Córdoba", "administrador", "Contadora", "+57 310 555 4321", True),
        ("Carlos Mejía", "cliente", "Revisor fiscal", "+57 315 222 1098", False),
    ]

    # El cliente es un tenant de la plataforma
    tenant = await db_session.get(Tenant, UUID(data["tenant_id"]))
    assert (tenant.kind, tenant.slug, tenant.name) == (
        TenantKind.CLIENT,
        "cliente-900123456",
        "Comercializadora Andina SAS",
    )

    # Las personas quedan en public.users, sin Cognito (aún no han entrado) e invitadas
    paula, carlos = (UUID(u["user_id"]) for u in data["users"])
    assert (await db_session.get(User, paula)).cognito_sub is None
    assert await role_of(db_session, paula, tenant.id) == ("administrador", "invited")
    assert await role_of(db_session, carlos, tenant.id) == ("cliente", "invited")
    assert await count(db_session, ClientContact) == 2


async def test_requires_clientes_crear_in_the_tenant(client, staff, platform, firm):
    assert (await client.post(URL, json=PAYLOAD)).status_code == 401

    # Sin decir en qué tenant trabaja
    admin = await staff("admin@jhrwise.com", SystemRole.ADMINISTRADOR)
    no_tenant = {"Authorization": admin["Authorization"]}
    assert (await client.post(URL, json=PAYLOAD, headers=no_tenant)).status_code == 400

    # Un asociado puede consultar clientes, pero no crearlos
    asociado = await staff("asociado@jhrwise.com", SystemRole.ASOCIADO)
    response = await client.post(URL, json=PAYLOAD, headers=asociado)
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"

    # Un administrador con la membresía revocada, tampoco
    revoked = await staff("ex@jhrwise.com", SystemRole.ADMINISTRADOR, MembershipStatus.REVOKED)
    assert (await client.post(URL, json=PAYLOAD, headers=revoked)).status_code == 403

    # Ni un administrador de la firma que dice trabajar en otro tenant
    other = await platform.tenant("otra-firma")
    headers = {**admin, "X-Tenant-Id": str(other)}
    assert (await client.post(URL, json=PAYLOAD, headers=headers)).status_code == 403


async def test_duplicate_nit_is_conflict(client, admin, db_session):
    assert (await client.post(URL, json=PAYLOAD, headers=admin)).status_code == 201

    other_people = payload(
        users=[{**PAYLOAD["users"][0], "email": "otra@andina.com.co"}],
    )
    response = await client.post(URL, json=other_people, headers=admin)
    assert response.status_code == 409
    assert await count(db_session, Client, Client.nit == "900123456") == 1


async def test_person_from_another_client_is_not_linked_yet(client, admin, db_session, platform):
    """La seguridad por filas no deja ver a una persona de otro tenant. Hasta que la
    plataforma tenga una función para buscarla por email, se rechaza sin guardar nada."""
    other_client = await platform.tenant("cliente-otro", TenantKind.CLIENT)
    carlos = await platform.user("carlos.mejia@revisoria.com.co", "Carlos Mejía")
    await platform.member(carlos, other_client, SystemRole.CLIENTE)

    response = await client.post(URL, json=PAYLOAD, headers=admin)

    assert response.status_code == 409
    assert response.json()["details"] == {"email": "carlos.mejia@revisoria.com.co"}
    assert await count(db_session, Client) == 0
    assert await count(db_session, Tenant, Tenant.slug == "cliente-900123456") == 0
    assert await count(db_session, User, User.email == "paula.cordoba@andina.com.co") == 0


async def test_firm_member_is_reused_without_changes(client, admin, db_session, staff):
    """Si la persona ya es visible (p. ej. alguien de la firma), se usa tal cual."""
    await staff("paula.cordoba@andina.com.co", SystemRole.ASOCIADO)

    response = await client.post(URL, json=PAYLOAD, headers=admin)

    assert response.status_code == 201, response.text
    assert response.json()["data"]["users"][0]["full_name"] == "Persona Prueba"
    assert await count(db_session, User, User.email == "paula.cordoba@andina.com.co") == 1


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
        (
            {"users": [{**PAYLOAD["users"][1], "is_primary_contact": True}, PAYLOAD["users"][0]]},
            "Exactly one",
        ),
        ({"users": [PAYLOAD["users"][1]]}, "Exactly one"),
        ({"users": []}, "at least 1"),
        ({"users": [PAYLOAD["users"][0], PAYLOAD["users"][0]]}, "repeated emails"),
    ],
    ids=[
        "dv",
        "juridica-sin-razon-social",
        "natural-sin-apellido",
        "municipio-otro-depto",
        "responsabilidad-repetida",
        "dos-contactos-principales",
        "sin-contacto-principal",
        "sin-usuarios",
        "correo-repetido",
    ],
)
async def test_invalid_payload_is_rejected(client, admin, db_session, changes, expected):
    response = await client.post(URL, json=payload(**changes), headers=admin)

    assert response.status_code == 422
    assert expected in str(response.json()["details"])
    assert await count(db_session, Client) == 0


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
    assert response.json()["data"]["display_name"] == "Juan Pablo Restrepo"


async def test_nothing_is_saved_if_something_fails(client, admin, db_session, monkeypatch):
    """Si falla a mitad de camino (aquí, al crear el 2.º usuario), no queda nada guardado:
    ni el tenant, ni las personas, ni los datos del RUT."""
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
    assert await count(db_session, Client) == 0
    assert await count(db_session, ClientContact) == 0
    assert await count(db_session, Tenant, Tenant.kind == TenantKind.CLIENT) == 0
    assert await count(db_session, Membership) == 1  # solo la del administrador de la firma
    assert await count(db_session, User, User.email == "paula.cordoba@andina.com.co") == 0


async def test_created_client_is_visible_only_inside_its_tenant(client, admin, db_session):
    """Comprueba la seguridad por filas: como wiseerp_app, el tenant nuevo solo se ve
    declarando que se trabaja en él."""
    data = (await client.post(URL, json=PAYLOAD, headers=admin)).json()["data"]
    tenant_id = data["tenant_id"]

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


async def test_token_of_unknown_person_is_forbidden(client, firm):
    headers = auth_headers(UUID("00000000-0000-0000-0000-000000000001"), firm)
    assert (await client.post(URL, json=PAYLOAD, headers=headers)).status_code == 403
