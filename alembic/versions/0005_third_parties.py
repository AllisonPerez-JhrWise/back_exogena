"""terceros: el maestro de terceros de cada cliente (tarea A1)

Revision ID: 0005_third_parties
Revises: 0004_dian_catalogs
Create Date: 2026-10-02 03:39:17.364124

Llave: empresa + tipo de identificación + número (texto, sin separadores).
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# identificadores de la revisión, usados por Alembic.
revision: str = "0005_third_parties"
down_revision: str | Sequence[str] | None = "0004_dian_catalogs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('third_parties',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('company_id', sa.Uuid(), nullable=False),
    sa.Column('identification_type', sqlmodel.sql.sqltypes.AutoString(length=2), nullable=False),
    sa.Column('identification_number', sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
    sa.Column('check_digit', sqlmodel.sql.sqltypes.AutoString(length=1), nullable=True),
    sa.Column('first_name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
    sa.Column('other_names', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
    sa.Column('first_last_name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
    sa.Column('second_last_name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
    sa.Column('legal_name', sqlmodel.sql.sqltypes.AutoString(length=250), nullable=True),
    sa.Column('country_code', sqlmodel.sql.sqltypes.AutoString(length=3), nullable=True),
    sa.Column('department_code', sqlmodel.sql.sqltypes.AutoString(length=2), nullable=True),
    sa.Column('city_code', sqlmodel.sql.sqltypes.AutoString(length=5), nullable=True),
    sa.Column('address', sqlmodel.sql.sqltypes.AutoString(length=250), nullable=True),
    sa.Column('email', sqlmodel.sql.sqltypes.AutoString(length=320), nullable=True),
    sa.CheckConstraint("check_digit ~ '^[0-9]$'", name=op.f('ck_third_parties_check_digit_digit')),
    sa.CheckConstraint("city_code ~ '^[0-9]{5}$'", name=op.f('ck_third_parties_city_code_digits')),
    sa.CheckConstraint("country_code ~ '^[0-9]{3}$'", name=op.f('ck_third_parties_country_code_digits')),
    sa.CheckConstraint("department_code ~ '^[0-9]{2}$'", name=op.f('ck_third_parties_department_code_digits')),
    sa.CheckConstraint("identification_number ~ '^[0-9A-Za-z]+$'", name=op.f('ck_third_parties_identification_number_clean')),
    sa.CheckConstraint("identification_type ~ '^[0-9]{2}$'", name=op.f('ck_third_parties_identification_type_digits')),
    sa.ForeignKeyConstraint(['company_id'], ['exogena.companies.id'], name=op.f('fk_third_parties_company_id_companies')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_third_parties')),
    schema='exogena'
    )
    op.create_index(op.f('ix_exogena_third_parties_company_id'), 'third_parties', ['company_id'], unique=False, schema='exogena')
    op.create_index(op.f('ix_exogena_third_parties_organization_id'), 'third_parties', ['organization_id'], unique=False, schema='exogena')
    op.create_index('ux_third_parties_company_identification', 'third_parties', ['company_id', 'identification_type', 'identification_number'], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))


def downgrade() -> None:
    op.drop_index('ux_third_parties_company_identification', table_name='third_parties', schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.drop_index(op.f('ix_exogena_third_parties_organization_id'), table_name='third_parties', schema='exogena')
    op.drop_index(op.f('ix_exogena_third_parties_company_id'), table_name='third_parties', schema='exogena')
    op.drop_table('third_parties', schema='exogena')
