"""Reglas de las tablas de empresas y grupos, verificadas contra PostgreSQL real.
Cada caso intenta romper una regla y comprueba que la base de datos lo impide."""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.clients.models import (
    Company,
    CompanyRutVersion,
    CompanyTaxResponsibility,
    CompanyUser,
    Group,
    PersonType,
    first_covered_tax_year,
    group_name_key,
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


def make_group(organization_id, name: str = "Grupo Muisca") -> Group:
    return Group(organization_id=organization_id, name=name, name_key=group_name_key(name))


def make_company(organization_id, nit: str = "900123456", **extra) -> Company:
    values = {
        "dv": "4",
        "person_type": PersonType.JURIDICA,
        "legal_name": "Comercializadora Andina SAS",
    }
    return Company(organization_id=organization_id, nit=nit, **{**values, **extra})


async def test_group_with_companies_versions_and_users(db_session, firm, platform):
    group = make_group(firm)
    await save(db_session, group)
    textiles = make_company(firm, "901223884", legal_name="Textiles Muisca SAS", group_id=group.id)
    zona_franca = make_company(
        firm, "901556201", legal_name="Textiles Muisca Zona Franca SAS", group_id=group.id
    )
    solo = make_company(firm, "800197268", legal_name="Andina SAS")  # sin grupo
    await save(db_session, textiles, zona_franca, solo)
    laura = await platform.user("laura@muisca.co")
    await save(
        db_session,
        *(CompanyTaxResponsibility(company_id=textiles.id, code=c) for c in ("05", "48")),
        CompanyRutVersion(company_id=textiles.id, generated_at=date(2026, 9, 5)),
        # Una persona ya invitada y otra pendiente de invitar
        CompanyUser(company_id=textiles.id, email="laura@muisca.co", full_name="L", user_id=laura),
        CompanyUser(company_id=textiles.id, email="pedro@muisca.co", full_name="Pedro"),
    )


async def test_group_name_is_unique_in_the_organization(db_session, firm, platform):
    await save(db_session, make_group(firm, "Grupo Sacyr"))
    # El mismo grupo escrito distinto: misma clave, no se permite
    await assert_rejected(db_session, make_group(firm, "  GRUPO   sacýr "))
    # En otra firma sí
    await save(db_session, make_group(await platform.tenant("otra-firma"), "Grupo Sacyr"))


def test_group_name_key():
    assert group_name_key("  GRUPO   Sacýr ") == group_name_key("Grupo Sacyr") == "grupo sacyr"
    assert group_name_key("Ñandú S.A.S") == "nandu s.a.s"


async def test_group_and_company_require_existing_organization(db_session):
    await assert_rejected(db_session, make_group(uuid4()))
    await assert_rejected(db_session, make_company(uuid4()))


async def test_company_requires_existing_group(db_session, firm):
    await assert_rejected(db_session, make_company(firm, group_id=uuid4()))


async def test_nit_is_unique_in_the_organization(db_session, firm):
    first = make_company(firm)
    await save(db_session, first)
    await assert_rejected(db_session, make_company(firm))

    # Con borrado lógico, el NIT se puede volver a usar
    first.is_deleted = True
    await save(db_session, first, make_company(firm))


async def test_same_nit_in_another_organization(db_session, platform):
    for firm_slug in ("firma-1", "firma-2"):
        await save(db_session, make_company(await platform.tenant(firm_slug)))


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
async def test_company_formats_are_enforced(db_session, firm, field, value):
    await assert_rejected(db_session, make_company(firm, **{field: value}))


async def test_name_depends_on_person_type(db_session, firm):
    await assert_rejected(db_session, make_company(firm, legal_name=None))
    await assert_rejected(
        db_session,
        make_company(firm, person_type=PersonType.NATURAL, legal_name=None, first_name="Juan"),
    )
    natural = make_company(
        firm,
        "1020304050",
        person_type=PersonType.NATURAL,
        legal_name=None,
        first_name="Juan",
        last_name="Restrepo",
    )
    await save(db_session, natural)
    assert natural.display_name == "Juan Restrepo"


async def test_company_user_rules(db_session, firm):
    andina, otra = make_company(firm), make_company(firm, "800197268")
    await save(db_session, andina, otra)
    await save(db_session, CompanyUser(company_id=andina.id, email="ana@x.co", full_name="Ana"))
    # La misma persona no se repite en una empresa, pero sí puede estar en otra
    await assert_rejected(
        db_session, CompanyUser(company_id=andina.id, email="ana@x.co", full_name="Ana")
    )
    await save(db_session, CompanyUser(company_id=otra.id, email="ana@x.co", full_name="Ana"))
    # El correo se guarda en minúsculas y la persona, si se indica, debe existir
    await assert_rejected(
        db_session, CompanyUser(company_id=andina.id, email="Luis@X.co", full_name="Luis")
    )
    await assert_rejected(
        db_session,
        CompanyUser(company_id=andina.id, email="luis@x.co", full_name="Luis", user_id=uuid4()),
    )


@pytest.mark.parametrize(
    "updated_at, year",
    [(date(2026, 9, 12), 2026), (date(2026, 1, 1), 2025), (date(2026, 1, 2), 2026)],
)
def test_first_covered_tax_year(updated_at, year):
    assert first_covered_tax_year(updated_at) == year
