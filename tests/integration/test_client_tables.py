"""Reglas de las tablas de clientes y empresas, verificadas contra PostgreSQL real.
Cada caso intenta romper una regla y comprueba que la base de datos lo impide."""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.clients.models import (
    Client,
    ClientMember,
    Company,
    CompanyRutVersion,
    CompanyTaxResponsibility,
    PersonType,
    first_covered_tax_year,
)
from app.modules.platform.models import SystemRole, TenantKind


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
def new_client(db_session, platform, firm):
    """Crea un cliente (con su cuenta en la plataforma) de la firma."""

    async def _new_client(slug: str = "cliente-andina") -> Client:
        tenant_id = await platform.tenant(slug, TenantKind.CLIENT)
        client = Client(organization_id=firm, tenant_id=tenant_id, name=slug)
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


async def test_group_with_companies_versions_and_members(db_session, new_client, platform):
    group = await new_client("grupo-muisca")
    textiles = make_company(group, "901223884", legal_name="Textiles Muisca SAS")
    zona_franca = make_company(group, "901556201", legal_name="Textiles Muisca Zona Franca SAS")
    await save(db_session, textiles, zona_franca)
    paula = await platform.member(
        await platform.user("paula@muisca.co"), group.tenant_id, SystemRole.CLIENTE
    )
    await save(
        db_session,
        *(CompanyTaxResponsibility(company_id=textiles.id, code=c) for c in ("05", "48")),
        CompanyRutVersion(company_id=textiles.id, generated_at=date(2026, 9, 5)),
        ClientMember(client_id=group.id, membership_id=paula, position="Contadora"),
    )


async def test_one_client_per_account(db_session, new_client):
    client = await new_client()
    await assert_rejected(
        db_session,
        Client(organization_id=client.organization_id, tenant_id=client.tenant_id, name="Otro"),
    )


async def test_client_requires_existing_account(db_session, firm):
    await assert_rejected(db_session, Client(organization_id=firm, tenant_id=uuid4(), name="X"))


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
        firm = await platform.tenant(firm_slug)
        client = Client(
            organization_id=firm,
            tenant_id=await platform.tenant(f"cliente-{firm_slug}", TenantKind.CLIENT),
            name="Andina",
        )
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


async def test_one_member_record_per_membership(db_session, new_client, platform):
    client = await new_client()
    ana_id = await platform.user("ana@x.co")
    ana = await platform.member(ana_id, client.tenant_id, SystemRole.CLIENTE)
    await save(db_session, ClientMember(client_id=client.id, membership_id=ana))
    await assert_rejected(db_session, ClientMember(client_id=client.id, membership_id=ana))
    await assert_rejected(db_session, ClientMember(client_id=client.id, membership_id=uuid4()))


@pytest.mark.parametrize(
    "updated_at, year",
    [(date(2026, 9, 12), 2026), (date(2026, 1, 1), 2025), (date(2026, 1, 2), 2026)],
)
def test_first_covered_tax_year(updated_at, year):
    assert first_covered_tax_year(updated_at) == year
