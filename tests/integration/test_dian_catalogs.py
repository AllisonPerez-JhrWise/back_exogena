"""Reglas de los catálogos de la DIAN, verificadas contra PostgreSQL real."""

import pytest
from sqlalchemy import select

from app.modules.dian.models import Country, Department, IdentificationType, Municipality
from tests.integration.test_client_tables import assert_rejected, save


def medellin(**changes) -> Municipality:
    data = {"code": "05001", "department_code": "05", "name": "Medellín", "year_from": 2025}
    return Municipality(**{**data, **changes})


def test_codes_keep_leading_zeros(db_session):
    """Regla del acuerdo: los códigos son texto y los ceros a la izquierda se conservan."""
    save(
        db_session,
        Department(code="05", name="Antioquia", year_from=2025),
        medellin(),
        Country(code="013", name="Afganistán", year_from=2025),
    )
    db_session.expunge_all()

    assert db_session.scalar(select(Department.code)) == "05"
    assert db_session.scalar(select(Municipality.code)) == "05001"
    assert db_session.scalar(select(Country.code)) == "013"


@pytest.mark.parametrize(
    "obj",
    [
        medellin(code="5001", department_code="50"),  # sin el cero
        medellin(department_code="08"),  # no es su departamento
        medellin(year_to=2024),  # termina antes de empezar
        Department(code="5", name="Antioquia", year_from=2025),
        Country(code="13", name="Afganistán", year_from=2025),
        IdentificationType(code="CC", name="Cédula de ciudadanía", year_from=2025),
    ],
    ids=["municipio-sin-cero", "otro-departamento", "vigencia-al-reves", "depto-1-digito",
         "pais-2-digitos", "tipo-con-letras"],
)  # fmt: skip
def test_formats_are_enforced(db_session, obj):
    assert_rejected(db_session, obj)


def test_same_code_once_per_list_but_again_in_a_new_one(db_session):
    """Una lista nueva de la DIAN repite los códigos con otro año de inicio."""
    save(db_session, medellin(year_to=2025))
    assert_rejected(db_session, medellin())
    save(db_session, medellin(year_from=2026))
