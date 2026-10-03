"""Reglas de las cifras del compromiso, verificadas contra PostgreSQL real."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.modules.engagements.models import Engagement, EngagementFigure, FigureConcept
from tests.integration.test_client_tables import assert_rejected, make_company, save


@pytest.fixture
def engagement(db_session, firm) -> Engagement:
    company = make_company(firm)
    save(db_session, company)
    engagement = Engagement(organization_id=firm, company_id=company.id, fiscal_year=2025)
    save(db_session, engagement)
    return engagement


def figure(engagement, **changes) -> EngagementFigure:
    data = {
        "organization_id": engagement.organization_id,
        "engagement_id": engagement.id,
        "concept": FigureConcept.GROSS_EQUITY,
        "tax_year": 2024,
        "value": 12_800_000_000,
        "source": "Declaración de renta del año anterior",
        "document_id": uuid4(),
    }
    return EngagementFigure(**{**data, **changes})


def test_large_values_are_kept_exactly_in_pesos(db_session, engagement):
    """12.800 millones no cabe en un entero normal: por eso es BIGINT."""
    save(db_session, figure(engagement))
    db_session.expunge_all()

    assert db_session.scalar(select(EngagementFigure.value)) == 12_800_000_000


def test_source_and_document_are_optional(db_session, engagement):
    save(db_session, figure(engagement, source=None, document_id=None))


def test_only_the_agreed_concepts(db_session, engagement):
    assert_rejected(db_session, figure(engagement, concept="ingresos_brutos"))


def test_one_figure_per_concept_and_year(db_session, engagement):
    save(db_session, figure(engagement))
    assert_rejected(db_session, figure(engagement, value=1))

    # Otro año u otro concepto sí
    save(
        db_session,
        figure(engagement, tax_year=2025),
        figure(engagement, concept=FigureConcept.GROSS_INCOME),
    )
