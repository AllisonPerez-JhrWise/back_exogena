"""POST /api/v1/clients: el formulario "Nuevo cliente" de punta a punta."""

import copy

import pytest
from sqlalchemy import func, select

from app.core.exceptions import BusinessRuleError
from app.modules.accounts.models import Role, RoleCode, User, UserRole
from app.modules.accounts.service import UserService
from app.modules.clients.models import Client, ClientUser
from app.modules.clients.nit import calculate_dv

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


async def test_admin_creates_client_with_users(client, admin, db_session):
    response = await client.post(URL, json=PAYLOAD, headers=await admin())

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["display_name"] == "Comercializadora Andina SAS"
    assert data["trade_name"] == "Andina Comercial"
    assert data["tax_responsibilities"] == ["05", "48", "42"]
    assert [(u["full_name"], u["position"], u["is_primary_contact"]) for u in data["users"]] == [
        ("Paula Córdoba", "Contadora", True),
        ("Carlos Mejía", "Revisor fiscal", False),
    ]

    # Los usuarios del cliente quedan sin acceso y con el rol usuario_cliente
    paula = (
        await db_session.execute(select(User).where(User.email == PAYLOAD["users"][0]["email"]))
    ).scalar_one()
    assert paula.can_login is False
    role_codes = await db_session.scalars(
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == paula.id)
    )
    assert list(role_codes) == [RoleCode.USUARIO_CLIENTE]


async def test_requires_admin(client, register):
    assert (await client.post(URL, json=PAYLOAD)).status_code == 401
    not_admin = await register("colaborador@jhrwise.com")
    response = await client.post(URL, json=PAYLOAD, headers=not_admin)
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


async def test_duplicate_nit_is_conflict(client, admin, db_session):
    headers = await admin()
    assert (await client.post(URL, json=PAYLOAD, headers=headers)).status_code == 201

    response = await client.post(URL, json=payload(users=[]), headers=headers)
    assert response.status_code == 409
    assert await count(db_session, Client, Client.nit == "900123456") == 1


async def test_existing_user_is_reused_without_changes(client, admin, db_session):
    # Carlos es revisor fiscal de Andina y luego de otra empresa
    headers = await admin()
    first = await client.post(URL, json=PAYLOAD, headers=headers)
    carlos_id = first.json()["data"]["users"][1]["user_id"]

    other = payload(
        rut={
            "nit": "800197268",
            "dv": "4",
            "legal_name": "Otra Empresa SAS",
            "tax_responsibilities": [],
        },
        users=[
            {
                "email": "Carlos.Mejia@revisoria.com.co",  # mismo correo, otra forma de escribirlo
                "first_name": "Carlitos",
                "last_name": "Otro",
                "position": "Revisor fiscal suplente",
            }
        ],
    )
    response = await client.post(URL, json=other, headers=headers)

    assert response.status_code == 201, response.text
    member = response.json()["data"]["users"][0]
    assert member["user_id"] == carlos_id
    assert member["full_name"] == "Carlos Mejía"  # sus datos no se sobrescriben
    assert member["position"] == "Revisor fiscal suplente"  # el cargo es propio de cada cliente
    assert await count(db_session, User, User.email == "carlos.mejia@revisoria.com.co") == 1


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
            "Only one",
        ),
        ({"users": [PAYLOAD["users"][0], PAYLOAD["users"][0]]}, "repeated emails"),
    ],
    ids=[
        "dv",
        "juridica-sin-razon-social",
        "natural-sin-apellido",
        "municipio-otro-depto",
        "responsabilidad-repetida",
        "dos-contactos-principales",
        "correo-repetido",
    ],
)
async def test_invalid_payload_is_rejected(client, admin, db_session, changes, expected):
    response = await client.post(URL, json=payload(**changes), headers=await admin())

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
    response = await client.post(URL, json=natural, headers=await admin())

    assert response.status_code == 201, response.text
    assert response.json()["data"]["display_name"] == "Juan Pablo Restrepo"


async def test_nothing_is_saved_if_something_fails(client, admin, db_session, monkeypatch):
    """Si falla a mitad de camino (aquí, al crear el 2.º usuario), no queda nada guardado."""
    headers = await admin()
    original = UserService.get_or_create_client_user
    calls = {"n": 0}

    async def fail_on_second_user(self, data, actor):
        calls["n"] += 1
        if calls["n"] == 2:
            raise BusinessRuleError("Simulated failure")
        return await original(self, data, actor)

    monkeypatch.setattr(UserService, "get_or_create_client_user", fail_on_second_user)
    response = await client.post(URL, json=PAYLOAD, headers=headers)

    assert response.status_code == 422
    assert await count(db_session, Client) == 0
    assert await count(db_session, ClientUser) == 0
    assert await count(db_session, User, User.email == "paula.cordoba@andina.com.co") == 0
