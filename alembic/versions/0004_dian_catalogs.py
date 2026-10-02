"""catálogos de la DIAN: países, departamentos, municipios y tipos de identificación (tarea A1)

Revision ID: 0004_dian_catalogs
Revises: 0003_companies_check_digit
Create Date: 2026-10-01 23:32:48.289125

Solo las tablas, vacías. Los datos (del archivo "Catálogos de la DIAN") se cargan aparte.
Son de la plataforma: no llevan organization_id.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# identificadores de la revisión, usados por Alembic.
revision: str = "0004_dian_catalogs"
down_revision: str | Sequence[str] | None = "0003_companies_check_digit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('countries',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('code', sqlmodel.sql.sqltypes.AutoString(length=3), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=150), nullable=False),
    sa.Column('year_from', sa.Integer(), nullable=False),
    sa.Column('year_to', sa.Integer(), nullable=True),
    sa.CheckConstraint("code ~ '^[0-9]{3}$'", name=op.f('ck_countries_code_digits')),
    sa.CheckConstraint('year_from BETWEEN 1990 AND 2100', name=op.f('ck_countries_year_from_range')),
    sa.CheckConstraint('year_to IS NULL OR year_to >= year_from', name=op.f('ck_countries_year_to_after_from')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_countries')),
    schema='exogena'
    )
    op.create_index('ux_countries_code_year_from', 'countries', ['code', 'year_from'], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.create_table('departments',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('code', sqlmodel.sql.sqltypes.AutoString(length=2), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=150), nullable=False),
    sa.Column('year_from', sa.Integer(), nullable=False),
    sa.Column('year_to', sa.Integer(), nullable=True),
    sa.CheckConstraint("code ~ '^[0-9]{2}$'", name=op.f('ck_departments_code_digits')),
    sa.CheckConstraint('year_from BETWEEN 1990 AND 2100', name=op.f('ck_departments_year_from_range')),
    sa.CheckConstraint('year_to IS NULL OR year_to >= year_from', name=op.f('ck_departments_year_to_after_from')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_departments')),
    schema='exogena'
    )
    op.create_index('ux_departments_code_year_from', 'departments', ['code', 'year_from'], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.create_table('identification_types',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('code', sqlmodel.sql.sqltypes.AutoString(length=2), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=150), nullable=False),
    sa.Column('usage', sqlmodel.sql.sqltypes.AutoString(length=250), nullable=True),
    sa.Column('year_from', sa.Integer(), nullable=False),
    sa.Column('year_to', sa.Integer(), nullable=True),
    sa.CheckConstraint("code ~ '^[0-9]{2}$'", name=op.f('ck_identification_types_code_digits')),
    sa.CheckConstraint('year_from BETWEEN 1990 AND 2100', name=op.f('ck_identification_types_year_from_range')),
    sa.CheckConstraint('year_to IS NULL OR year_to >= year_from', name=op.f('ck_identification_types_year_to_after_from')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_identification_types')),
    schema='exogena'
    )
    op.create_index('ux_identification_types_code_year_from', 'identification_types', ['code', 'year_from'], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.create_table('municipalities',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('code', sqlmodel.sql.sqltypes.AutoString(length=5), nullable=False),
    sa.Column('department_code', sqlmodel.sql.sqltypes.AutoString(length=2), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=150), nullable=False),
    sa.Column('year_from', sa.Integer(), nullable=False),
    sa.Column('year_to', sa.Integer(), nullable=True),
    sa.CheckConstraint("code ~ '^[0-9]{5}$'", name=op.f('ck_municipalities_code_digits')),
    sa.CheckConstraint('department_code = left(code, 2)', name=op.f('ck_municipalities_department_code_matches')),
    sa.CheckConstraint('year_from BETWEEN 1990 AND 2100', name=op.f('ck_municipalities_year_from_range')),
    sa.CheckConstraint('year_to IS NULL OR year_to >= year_from', name=op.f('ck_municipalities_year_to_after_from')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_municipalities')),
    schema='exogena'
    )
    op.create_index(op.f('ix_exogena_municipalities_department_code'), 'municipalities', ['department_code'], unique=False, schema='exogena')
    op.create_index('ux_municipalities_code_year_from', 'municipalities', ['code', 'year_from'], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))


def downgrade() -> None:
    op.drop_index('ux_municipalities_code_year_from', table_name='municipalities', schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.drop_index(op.f('ix_exogena_municipalities_department_code'), table_name='municipalities', schema='exogena')
    op.drop_table('municipalities', schema='exogena')
    op.drop_index('ux_identification_types_code_year_from', table_name='identification_types', schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.drop_table('identification_types', schema='exogena')
    op.drop_index('ux_departments_code_year_from', table_name='departments', schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.drop_table('departments', schema='exogena')
    op.drop_index('ux_countries_code_year_from', table_name='countries', schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.drop_table('countries', schema='exogena')
