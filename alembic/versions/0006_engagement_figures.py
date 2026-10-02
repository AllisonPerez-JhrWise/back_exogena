"""cifras del compromiso: las que usan las reglas, ya calculadas (tarea A1)

Revision ID: 0006_engagement_figures
Revises: 0005_third_parties
Create Date: 2026-10-02 03:56:58.046379

Valores en pesos enteros (BIGINT). Una cifra por compromiso, concepto y año.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# identificadores de la revisión, usados por Alembic.
revision: str = "0006_engagement_figures"
down_revision: str | Sequence[str] | None = "0005_third_parties"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('engagement_figures',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('engagement_id', sa.Uuid(), nullable=False),
    sa.Column('concept', sqlmodel.sql.sqltypes.AutoString(length=40), nullable=False),
    sa.Column('tax_year', sa.Integer(), nullable=False),
    sa.Column('value', sa.BigInteger(), nullable=False),
    sa.Column('source', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
    sa.Column('document_id', sa.Uuid(), nullable=True),
    sa.CheckConstraint("concept IN ('gross_income', 'gross_equity', 'annual_vat_income', 'capital_and_non_labor_income')", name=op.f('ck_engagement_figures_concept_valid')),
    sa.CheckConstraint('tax_year BETWEEN 2000 AND 2100', name=op.f('ck_engagement_figures_tax_year_range')),
    sa.ForeignKeyConstraint(['engagement_id'], ['exogena.engagements.id'], name=op.f('fk_engagement_figures_engagement_id_engagements')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_engagement_figures')),
    schema='exogena'
    )
    op.create_index(op.f('ix_exogena_engagement_figures_engagement_id'), 'engagement_figures', ['engagement_id'], unique=False, schema='exogena')
    op.create_index(op.f('ix_exogena_engagement_figures_organization_id'), 'engagement_figures', ['organization_id'], unique=False, schema='exogena')
    op.create_index('ux_engagement_figures_engagement_concept_year', 'engagement_figures', ['engagement_id', 'concept', 'tax_year'], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))


def downgrade() -> None:
    op.drop_index('ux_engagement_figures_engagement_concept_year', table_name='engagement_figures', schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.drop_index(op.f('ix_exogena_engagement_figures_organization_id'), table_name='engagement_figures', schema='exogena')
    op.drop_index(op.f('ix_exogena_engagement_figures_engagement_id'), table_name='engagement_figures', schema='exogena')
    op.drop_table('engagement_figures', schema='exogena')
