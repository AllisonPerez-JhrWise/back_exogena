"""Reglas de las tablas de clientes y empresas, verificadas contra PostgreSQL real.
Cada caso intenta romper una regla y comprueba que la base de datos lo impide."""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.clients.models import (
    Client,
    ClientUser,
    Company,
    CompanyRutVersion,
    CompanyTaxResponsibility,
    PersonType,
    first_covered_tax_year,
)


async def save(session, *objs) -> None:
    session.add_all(objs)
    await session.flush()


async def assert_rejected(session, *objs) -> None:
    """La base de datos debe rechazar estos registros (el savepoint aísla el error)."""
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add_all(objs)
            await session.flush()


@pytest.fixture
def new_client(db_session, firm):
    """Crea un cliente (grupo) de la firma."""

    async def _new_client(name: str = "Andina") -> Client:
        client = Client(organization_id=firm, name=name)
        await save(db_session, client)
        return client

    return _new_client


def make_company(client: Client, nit: str = "900123456", **extra) -> Company:
    values = {
        "dv": "4",
        "person_type": PersonType.JURIDICA,
        "legal_name": "Comercializadora Andina SAS",
    }
    return Company(
        client_id=client.id, organization_id=client.organization_id, nit=nit, **{**values, **extra}
    )


async def test_group_with_companies_versions_and_users(db_session, new_client, platform):
    group = await new_client("Grupo Muisca")
    textiles = make_company(group, "901223884", legal_name="Textiles Muisca SAS")
    zona_franca = make_company(group, "901556201", legal_name="Textiles Muisca Zona Franca SAS")
    await save(db_session, textiles, zona_franca)
    laura = await platform.user("laura@muisca.co")
    await save(
        db_session,
        *(CompanyTaxResponsibility(company_id=textiles.id, code=c) for c in ("05", "48")),
        CompanyRutVersion(company_id=textiles.id, generated_at=date(2026, 9, 5)),
        # Una persona ya invitada y otra pendiente de invitar
        ClientUser(client_id=group.id, email="laura@muisca.co", full_name="Laura", user_id=laura),
        ClientUser(client_id=group.id, email="pedro@muisca.co", full_name="Pedro"),
    )


async def test_client_requires_existing_organization(db_session):
    await assert_rejected(db_session, Client(organization_id=uuid4(), name="X"))


async def test_nit_is_unique_in_the_organization(db_session, new_client, platform):
    first = make_company(await new_client("c-1"))
    await save(db_session, first)
    # Aunque sea de otro cliente de la misma firma
    await assert_rejected(db_session, make_company(await new_client("c-2")))

    # Con borrado lógico, el NIT se puede volver a usar
    first.is_deleted = True
    await save(db_session, first, make_company(await new_client("c-3")))


async def test_same_nit_in_another_organization(db_session, platform):
    for firm_slug in ("firma-1", "firma-2"):
        client = Client(organization_id=await platform.tenant(firm_slug), name="Andina")
        await save(db_session, client)
        await save(db_session, make_company(client))


@pytest.mark.parametrize(
    "field, value",
    [
        ("nit", "900-123"),
        ("dv", "X"),
        ("person_type", "empresa"),
        ("department_code", "1"),
        ("city_code", "BOGOT"),
        ("main_activity_code", "47"),
    ],
)
async def test_company_formats_are_enforced(db_session, new_client, field, value):
    await assert_rejected(db_session, make_company(await new_client(), **{field: value}))


async def test_name_depends_on_person_type(db_session, new_client):
    client = await new_client()
    await assert_rejected(db_session, make_company(client, legal_name=None))
    await assert_rejected(
        db_session,
        make_company(client, person_type=PersonType.NATURAL, legal_name=None, first_name="Juan"),
    )
    natural = make_company(
        client,
        "1020304050",
        person_type=PersonType.NATURAL,
        legal_name=None,
        first_name="Juan",
        last_name="Restrepo",
    )
    await save(db_session, natural)
    assert natural.display_name == "Juan Restrepo"


async def test_client_user_rules(db_session, new_client):
    andina, otro = await new_client("Andina"), await new_client("Otro")
    await save(db_session, ClientUser(client_id=andina.id, email="ana@x.co", full_name="Ana"))
    # La misma persona no se repite en un cliente, pero sí puede estar en otro
    await assert_rejected(
        db_session, ClientUser(client_id=andina.id, email="ana@x.co", full_name="Ana")
    )
    await save(db_session, ClientUser(client_id=otro.id, email="ana@x.co", full_name="Ana"))
    # El correo se guarda en minúsculas y la persona, si se indica, debe existir
    await assert_rejected(
        db_session, ClientUser(client_id=andina.id, email="Luis@X.co", full_name="Luis")
    )
    await assert_rejected(
        db_session,
        ClientUser(client_id=andina.id, email="luis@x.co", full_name="Luis", user_id=uuid4()),
    )


@pytest.mark.parametrize(
    "updated_at, year",
    [(date(2026, 9, 12), 2026), (date(2026, 1, 1), 2025), (date(2026, 1, 2), 2026)],
)
def test_first_covered_tax_year(updated_at, year):
    assert first_covered_tax_year(updated_at) == year
