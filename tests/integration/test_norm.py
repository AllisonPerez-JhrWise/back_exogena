"""Reglas de las tablas de la norma (UVT, topes, casillas del RUT y formatos),
verificadas contra PostgreSQL real.

Los valores son de ejemplo para probar las reglas, no los datos oficiales."""

import pytest

from app.modules.norm.models import (
    Format,
    FormatConcept,
    RutBox,
    RutBoxCode,
    Threshold,
    ThresholdAppliesTo,
    UvtValue,
)
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


def test_one_uvt_value_per_year(db_session):
    save(db_session, uvt())
    assert_rejected(db_session, uvt(value=60_000))
    save(db_session, uvt(year=2026))


def test_same_threshold_once_per_validity(db_session):
    save(db_session, threshold(year_to=2025))
    assert_rejected(db_session, threshold())
    # Si la norma cambia, el tope nuevo rige desde otro año
    save(db_session, threshold(year_from=2026, value_uvt=3_000))


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
def test_values_are_enforced(db_session, obj):
    assert_rejected(db_session, obj)


def test_rut_box_dictionary(db_session):
    """Es el diccionario de la norma: no guarda el RUT de ningún cliente."""
    box = RutBox(box_code="53", name="Responsabilidades, calidades y atributos")
    save(db_session, box)
    save(db_session, RutBoxCode(rut_box_id=box.id, code="05", name="Renta"))
    assert_rejected(db_session, RutBoxCode(rut_box_id=box.id, code="05", name="Otra"))
    assert_rejected(db_session, RutBox(box_code="53", name="Repetida"))
    assert_rejected(db_session, RutBox(box_code="5A", name="Con letra"))


def test_formats_and_concepts(db_session):
    f1001 = Format(number="1001", version=10, name="Pagos o abonos en cuenta", year_from=2025)
    save(db_session, f1001)
    # Una versión nueva de la DIAN es otra fila
    save(db_session, Format(number="1001", version=11, name="Pagos", year_from=2026))
    assert_rejected(db_session, Format(number="1001", version=10, name="X", year_from=2025))
    assert_rejected(db_session, Format(number="101", version=1, name="X", year_from=2025))

    concept = FormatConcept(
        format_id=f1001.id, code="5002", description="Honorarios", year_from=2025
    )
    save(db_session, concept)
    assert_rejected(
        db_session,
        FormatConcept(format_id=f1001.id, code="5002", description="Repetido", year_from=2025),
    )
