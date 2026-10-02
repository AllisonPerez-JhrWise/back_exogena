"""Reglas de la tabla de terceros, verificadas contra PostgreSQL real."""

import pytest
from sqlalchemy import select

from app.modules.third_parties.models import ThirdParty
from tests.integration.test_client_tables import assert_rejected, make_company, save


@pytest.fixture
async def company(db_session, firm):
    company = make_company(firm)
    await save(db_session, company)
    return company


def person(company, **changes) -> ThirdParty:
    data = {
        "organization_id": company.organization_id,
        "company_id": company.id,
        "identification_type": "13",
        "identification_number": "0012345",
        "first_name": "Juan",
        "other_names": "Carlos",
        "first_last_name": "Pérez",
        "second_last_name": "Gómez",
        "country_code": "169",
        "department_code": "05",
        "city_code": "05001",
    }
    return ThirdParty(**{**data, **changes})


async def test_identification_keeps_leading_zeros(db_session, company):
    """Prueba obligatoria del acuerdo: 0012345 se guarda y se lee como 0012345."""
    await save(db_session, person(company))
    db_session.expunge_all()

    saved = await db_session.scalar(select(ThirdParty))
    assert saved.identification_number == "0012345"
    assert (saved.country_code, saved.department_code, saved.city_code) == ("169", "05", "05001")


async def test_company_with_nit_and_check_digit(db_session, company):
    await save(
        db_session,
        person(
            company,
            identification_type="31",
            identification_number="800197268",
            check_digit="4",
            first_name=None,
            other_names=None,
            first_last_name=None,
            second_last_name=None,
            legal_name="Andina Zona Franca SAS",
        ),
    )


async def test_passport_can_have_letters(db_session, company):
    await save(
        db_session, person(company, identification_type="41", identification_number="AB123456")
    )


async def test_incomplete_data_is_saved_for_the_review_to_find(db_session, company):
    """Sin apellido ni ubicación: se guarda; la revisión de exógena lo muestra como hallazgo."""
    await save(
        db_session,
        person(
            company,
            first_last_name=None,
            country_code=None,
            department_code=None,
            city_code=None,
        ),
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"identification_number": "001.234.5"},  # con puntos
        {"identification_number": "0012345-6"},  # con guion
        {"identification_number": "0012 345"},  # con espacio
        {"identification_type": "CC"},
        {"check_digit": "X"},
        {"country_code": "CO"},
        {"department_code": "5"},
        {"city_code": "5001"},
    ],
    ids=["puntos", "guion", "espacio", "tipo-con-letras", "dv-letra", "pais-letras",
         "depto-sin-cero", "ciudad-sin-cero"],
)  # fmt: skip
async def test_formats_are_enforced(db_session, company, changes):
    await assert_rejected(db_session, person(company, **changes))


async def test_same_third_party_once_per_company(db_session, company, firm):
    await save(db_session, person(company))
    await assert_rejected(db_session, person(company))

    # El mismo número con otro tipo es otro tercero
    await save(db_session, person(company, identification_type="12"))
    # Y el mismo tercero puede estar en otro cliente
    other = make_company(firm, "800197268", check_digit="4")
    await save(db_session, other)
    await save(db_session, person(other))
