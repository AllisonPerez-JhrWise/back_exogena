"""la norma, parte 2: diccionario de casillas del RUT, formatos y conceptos (tarea A1)

Revision ID: 0008_rut_boxes_and_formats
Revises: 0007_uvt_and_thresholds
Create Date: 2026-10-02 04:24:44.526473

Solo catálogos, vacíos: ninguna tabla guarda datos de un cliente (su RUT lo tiene
extracción). Son de la plataforma: no llevan organization_id.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# identificadores de la revisión, usados por Alembic.
revision: str = "0008_rut_boxes_and_formats"
down_revision: str | Sequence[str] | None = "0007_uvt_and_thresholds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('formats',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('number', sqlmodel.sql.sqltypes.AutoString(length=4), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=250), nullable=False),
    sa.Column('article', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
    sa.Column('year_from', sa.Integer(), nullable=False),
    sa.Column('year_to', sa.Integer(), nullable=True),
    sa.CheckConstraint("number ~ '^[0-9]{4}$'", name=op.f('ck_formats_number_digits')),
    sa.CheckConstraint('version > 0', name=op.f('ck_formats_version_positive')),
    sa.CheckConstraint('year_from BETWEEN 2000 AND 2100', name=op.f('ck_formats_year_from_range')),
    sa.CheckConstraint('year_to IS NULL OR year_to >= year_from', name=op.f('ck_formats_year_to_after_from')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_formats')),
    schema='exogena'
    )
    op.create_index('ux_formats_number_version', 'formats', ['number', 'version'], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.create_table('rut_boxes',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('box_code', sqlmodel.sql.sqltypes.AutoString(length=3), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=250), nullable=False),
    sa.Column('description', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
    sa.Column('used_by_rule', sqlmodel.sql.sqltypes.AutoString(length=250), nullable=True),
    sa.Column('purpose', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    sa.CheckConstraint("box_code ~ '^[0-9]{1,3}$'", name=op.f('ck_rut_boxes_box_code_digits')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rut_boxes')),
    schema='exogena'
    )
    op.create_index('ux_rut_boxes_box_code', 'rut_boxes', ['box_code'], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.create_table('format_concepts',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('format_id', sa.Uuid(), nullable=False),
    sa.Column('code', sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
    sa.Column('description', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
    sa.Column('expected_third_party', sqlmodel.sql.sqltypes.AutoString(length=250), nullable=True),
    sa.Column('year_from', sa.Integer(), nullable=False),
    sa.Column('year_to', sa.Integer(), nullable=True),
    sa.CheckConstraint('year_from BETWEEN 2000 AND 2100', name=op.f('ck_format_concepts_year_from_range')),
    sa.CheckConstraint('year_to IS NULL OR year_to >= year_from', name=op.f('ck_format_concepts_year_to_after_from')),
    sa.ForeignKeyConstraint(['format_id'], ['exogena.formats.id'], name=op.f('fk_format_concepts_format_id_formats')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_format_concepts')),
    schema='exogena'
    )
    op.create_index(op.f('ix_exogena_format_concepts_format_id'), 'format_concepts', ['format_id'], unique=False, schema='exogena')
    op.create_index('ux_format_concepts_format_code_year_from', 'format_concepts', ['format_id', 'code', 'year_from'], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.create_table('rut_box_codes',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('rut_box_id', sa.Uuid(), nullable=False),
    sa.Column('code', sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=250), nullable=False),
    sa.ForeignKeyConstraint(['rut_box_id'], ['exogena.rut_boxes.id'], name=op.f('fk_rut_box_codes_rut_box_id_rut_boxes')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rut_box_codes')),
    schema='exogena'
    )
    op.create_index(op.f('ix_exogena_rut_box_codes_rut_box_id'), 'rut_box_codes', ['rut_box_id'], unique=False, schema='exogena')
    op.create_index('ux_rut_box_codes_box_code', 'rut_box_codes', ['rut_box_id', 'code'], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))


def downgrade() -> None:
    op.drop_index('ux_rut_box_codes_box_code', table_name='rut_box_codes', schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.drop_index(op.f('ix_exogena_rut_box_codes_rut_box_id'), table_name='rut_box_codes', schema='exogena')
    op.drop_table('rut_box_codes', schema='exogena')
    op.drop_index('ux_format_concepts_format_code_year_from', table_name='format_concepts', schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.drop_index(op.f('ix_exogena_format_concepts_format_id'), table_name='format_concepts', schema='exogena')
    op.drop_table('format_concepts', schema='exogena')
    op.drop_index('ux_rut_boxes_box_code', table_name='rut_boxes', schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.drop_table('rut_boxes', schema='exogena')
    op.drop_index('ux_formats_number_version', table_name='formats', schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.drop_table('formats', schema='exogena')
