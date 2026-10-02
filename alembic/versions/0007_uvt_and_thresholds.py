"""la norma, parte 1: valor de la UVT por año y topes en UVT (tarea A1)

Revision ID: 0007_uvt_and_thresholds
Revises: 0006_engagement_figures
Create Date: 2026-10-02 04:11:22.705154

Solo las tablas, vacías: los datos se cargan cuando se confirmen con la fuente oficial.
Son de la plataforma: no llevan organization_id.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# identificadores de la revisión, usados por Alembic.
revision: str = "0007_uvt_and_thresholds"
down_revision: str | Sequence[str] | None = "0006_engagement_figures"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('thresholds',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('code', sqlmodel.sql.sqltypes.AutoString(length=60), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=250), nullable=False),
    sa.Column('value_uvt', sa.Integer(), nullable=False),
    sa.Column('applies_to', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
    sa.Column('year_from', sa.Integer(), nullable=False),
    sa.Column('year_to', sa.Integer(), nullable=True),
    sa.Column('norm', sqlmodel.sql.sqltypes.AutoString(length=250), nullable=True),
    sa.Column('norm_url', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    sa.CheckConstraint("applies_to IN ('legal_entity', 'natural_person', 'any')", name=op.f('ck_thresholds_applies_to_valid')),
    sa.CheckConstraint('value_uvt > 0', name=op.f('ck_thresholds_value_uvt_positive')),
    sa.CheckConstraint('year_from BETWEEN 2000 AND 2100', name=op.f('ck_thresholds_year_from_range')),
    sa.CheckConstraint('year_to IS NULL OR year_to >= year_from', name=op.f('ck_thresholds_year_to_after_from')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_thresholds')),
    schema='exogena'
    )
    op.create_index('ux_thresholds_code_year_from', 'thresholds', ['code', 'year_from'], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.create_table('uvt_values',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('value', sa.BigInteger(), nullable=False),
    sa.Column('resolution', sqlmodel.sql.sqltypes.AutoString(length=250), nullable=False),
    sa.Column('norm_url', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    sa.CheckConstraint('value > 0', name=op.f('ck_uvt_values_value_positive')),
    sa.CheckConstraint('year BETWEEN 2000 AND 2100', name=op.f('ck_uvt_values_year_range')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_uvt_values')),
    schema='exogena'
    )
    op.create_index('ux_uvt_values_year', 'uvt_values', ['year'], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))


def downgrade() -> None:
    op.drop_index('ux_uvt_values_year', table_name='uvt_values', schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.drop_table('uvt_values', schema='exogena')
    op.drop_index('ux_thresholds_code_year_from', table_name='thresholds', schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.drop_table('thresholds', schema='exogena')
