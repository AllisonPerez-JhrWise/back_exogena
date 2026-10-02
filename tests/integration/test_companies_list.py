"""GET /api/v1/companies: la pantalla de clientes (una fila por empresa)."""

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text, update

from app.modules.clients.models import Company, CompanyUser
from app.modules.clients.nit import calculate_dv
from app.modules.platform.models import SystemRole
from tests.integration.conftest import auth_headers
from tests.integration.test_create_client import OTHER_COMPANY_RUT, payload
from tests.integration.test_create_client import URL as CLIENTS_URL
from tests.integration.test_engagements import engagement, team  # noqa: F401 (fixture)

URL = "/api/v1/companies"


@dataclass
class Screen:
    andina: dict  # cliente con una empresa y un compromiso activo
    muisca: dict  # grupo: primera empresa
    zona_franca: dict  # grupo: segunda empresa
    importadora: dict  # RUT de hace 14 meses
    muisca_servicios: dict  # RUT sin fecha de generación identificada
    distribuidora: dict  # inactiva


async def create(client, admin, **changes) -> dict:
    # Solo Andina conserva el nombre comercial del ejemplo ("Andina Comercial")
    changes.setdefault("organization", {"trade_name": None})
    response = await client.post(CLIENTS_URL, json=payload(**changes), headers=admin)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def rut(nit: str, name: str) -> dict:
    return {
        "nit": nit,
        "check_digit": calculate_dv(nit),
        "legal_name": name,
        "tax_responsibilities": [],
    }


@pytest.fixture
async def screen(client, admin, team, db_session) -> Screen:  # noqa: F811
    andina = await create(
        client,
        admin,
        organization={"trade_name": "Andina Comercial"},
        engagements=[engagement(team)],
        users=[],
    )
    muisca = await create(
        client,
        admin,
        group_name="Grupo Muisca",
        rut=rut("901223884", "Textiles Muisca SAS"),
        users=[],
    )
    zona_franca = await create(
        client, admin, group_id=muisca["company"]["group"]["id"], rut=OTHER_COMPANY_RUT, users=[]
    )
    importadora = await create(
        client, admin, rut=rut("830456789", "Importadora Andes SAS"), users=[]
    )
    servicios = await create(client, admin, rut=rut("901778030", "Muisca Servicios SAS"), users=[])
    distribuidora = await create(
        client, admin, rut=rut("900987654", "Distribuidora del Norte SAS"), users=[]
    )

    # Casos que el asistente no deja crear: se preparan directo en la base
    async def set_company(data: dict, **values):
        await db_session.execute(
            update(Company).where(Company.id == UUID(data["company"]["id"])).values(**values)
        )

    await set_company(importadora, rut_generated_at=date.today() - timedelta(days=430))
    await set_company(servicios, rut_generated_at=None)
    await set_company(distribuidora, is_active=False)
    await db_session.commit()
    return Screen(andina, muisca, zona_franca, importadora, servicios, distribuidora)


def rows(response) -> list[dict]:
    assert response.status_code == 200, response.text
    return response.json()["data"]["items"]


async def test_admin_sees_every_company_of_the_organization(client, admin, screen):
    response = await client.get(URL, headers=admin)
    items = {row["display_name"]: row for row in rows(response)}

    assert response.json()["data"]["total"] == 6
    assert list(items) == [  # por nombre
        "Andina Zona Franca SAS",
        "Comercializadora Andina SAS",
        "Distribuidora del Norte SAS",
        "Importadora Andes SAS",
        "Muisca Servicios SAS",
        "Textiles Muisca SAS",
    ]
    andina = items["Comercializadora Andina SAS"]
    assert (
        andina["nit"],
        andina["check_digit"],
        andina["group"],
        andina["active_engagements"],
    ) == (
        "900123456",
        "8",
        None,  # sin grupo
        1,
    )
    assert andina["status"] == "activo"
    # Las dos empresas del grupo muestran su nombre
    assert items["Textiles Muisca SAS"]["group"] == "Grupo Muisca"
    assert items["Andina Zona Franca SAS"]["group"] == "Grupo Muisca"
    # Estados calculados
    assert items["Importadora Andes SAS"]["status"] == "rut_por_renovar"
    servicios = items["Muisca Servicios SAS"]
    assert (servicios["status"], servicios["rut_date_unknown"]) == ("rut_por_renovar", True)
    assert items["Distribuidora del Norte SAS"]["status"] == "inactivo"


@pytest.mark.parametrize(
    "params, expected",
    [
        ({"company": "muisca"}, ["Muisca Servicios SAS", "Textiles Muisca SAS"]),
        ({"company": "Andina Comercial"}, ["Comercializadora Andina SAS"]),  # nombre comercial
        ({"nit": "9012"}, ["Textiles Muisca SAS"]),
        ({"group": "MUISCA"}, ["Andina Zona Franca SAS", "Textiles Muisca SAS"]),
        ({"engagements_min": 1}, ["Comercializadora Andina SAS"]),
        ({"status": "rut_por_renovar,inactivo"}, [
            "Distribuidora del Norte SAS", "Importadora Andes SAS", "Muisca Servicios SAS",
        ]),
    ],
    ids=["empresa", "nombre-comercial", "nit", "grupo", "compromisos", "estados"],
)  # fmt: skip
async def test_filters(client, admin, screen, params, expected):
    assert [
        row["display_name"] for row in rows(await client.get(URL, params=params, headers=admin))
    ] == expected


async def test_filter_by_group_shows_its_companies_together(client, admin, screen):
    response = await client.get(
        URL, params={"group_id": screen.muisca["company"]["group"]["id"]}, headers=admin
    )
    assert [row["display_name"] for row in rows(response)] == [
        "Andina Zona Franca SAS",
        "Textiles Muisca SAS",
    ]


async def test_sort_and_pagination(client, admin, screen):
    response = await client.get(URL, params={"sort": "-rut_generated_at", "size": 2}, headers=admin)
    data = response.json()["data"]
    assert (data["total"], data["pages"], len(data["items"])) == (6, 3, 2)

    last_page = await client.get(
        URL, params={"sort": "-rut_generated_at", "size": 2, "page": 3}, headers=admin
    )
    # Sin fecha de generación va al final
    assert rows(last_page)[-1]["display_name"] == "Muisca Servicios SAS"

    assert (await client.get(URL, params={"sort": "clave"}, headers=admin)).status_code == 400
    assert (await client.get(URL, params={"status": "otro"}, headers=admin)).status_code == 422


async def test_partner_sees_only_the_companies_of_his_engagements(client, screen, team, firm):  # noqa: F811
    socio = auth_headers(team.socio, firm)
    assert [row["display_name"] for row in rows(await client.get(URL, headers=socio))] == [
        "Comercializadora Andina SAS"
    ]


async def test_associate_without_engagements_sees_nothing(client, screen, staff):
    asociado = await staff("asociado@jhrwise.com", SystemRole.ASOCIADO)
    assert rows(await client.get(URL, headers=asociado)) == []


async def test_client_user_sees_only_its_company(client, screen, platform, firm, db_session):
    """El usuario del cliente tiene su acceso en la firma (rol cliente) y ve solo las
    empresas que tiene asignadas (company_users), aunque estén en un grupo."""
    laura = await platform.user("laura@muisca.co")
    await platform.member(laura, firm, SystemRole.CLIENTE)
    db_session.add(
        CompanyUser(
            company_id=UUID(screen.muisca["company"]["id"]),
            email="laura@muisca.co",
            full_name="Laura",
            user_id=laura,
        )
    )
    await db_session.commit()

    response = await client.get(URL, headers=auth_headers(laura, firm))
    # Textiles Muisca SAS está en el grupo con Andina Zona Franca SAS, que no ve
    assert [row["display_name"] for row in rows(response)] == ["Textiles Muisca SAS"]


async def test_requires_clientes_leer(client, screen, platform, firm):
    outsider = auth_headers(await platform.user("externo@x.co"), firm)
    assert (await client.get(URL)).status_code == 401
    assert (await client.get(URL, headers=outsider)).status_code == 403


async def test_deleted_companies_are_not_listed(client, admin, screen, db_session):
    await db_session.execute(
        text("UPDATE exogena.companies SET is_deleted = true WHERE nit = '900987654'")
    )
    await db_session.commit()
    assert (await client.get(URL, headers=admin)).json()["data"]["total"] == 5
