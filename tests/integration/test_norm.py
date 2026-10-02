"""Reglas de las tablas de la norma (UVT y topes), verificadas contra PostgreSQL real.

Los valores son de ejemplo para probar las reglas, no los datos oficiales."""

import pytest

from app.modules.norm.models import Threshold, ThresholdAppliesTo, UvtValue
from tests.integration.test_client_tables import assert_rejected, save


def uvt(**changes) -> UvtValue:
    data = {"year": 2025, "value": 50_000, "resolution": "Resolución de prueba"}
    return UvtValue(**{**data, **changes})


def threshold(**changes) -> Threshold:
    data = {
        "code": "gross_income_legal_entity",
        "name": "Ingresos brutos de persona jurídica",
        "value_uvt": 2_400,
        "applies_to": ThresholdAppliesTo.LEGAL_ENTITY,
        "year_from": 2025,
    }
    return Threshold(**{**data, **changes})


async def test_one_uvt_value_per_year(db_session):
    await save(db_session, uvt())
    await assert_rejected(db_session, uvt(value=60_000))
    await save(db_session, uvt(year=2026))


async def test_same_threshold_once_per_validity(db_session):
    await save(db_session, threshold(year_to=2025))
    await assert_rejected(db_session, threshold())
    # Si la norma cambia, el tope nuevo rige desde otro año
    await save(db_session, threshold(year_from=2026, value_uvt=3_000))


@pytest.mark.parametrize(
    "obj",
    [
        uvt(value=0),
        threshold(applies_to="juridica"),
        threshold(value_uvt=0),
        threshold(year_to=2024),  # termina antes de empezar
    ],
    ids=["uvt-en-cero", "aplica-a-invalido", "tope-en-cero", "vigencia-al-reves"],
)
async def test_values_are_enforced(db_session, obj):
    await assert_rejected(db_session, obj)
