"""empresas: dv pasa a llamarse check_digit (tarea A1)

Revision ID: 0003_companies_check_digit
Revises: 0002_engagements_data_agreement
Create Date: 2026-10-01

Es el nombre acordado en todos los servicios para el dígito de verificación del NIT.
Solo cambia el nombre: los datos se conservan.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_companies_check_digit"
down_revision: str | Sequence[str] | None = "0002_engagements_data_agreement"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "exogena"
TABLE = "companies"


def upgrade() -> None:
    op.alter_column(TABLE, "dv", new_column_name="check_digit", schema=SCHEMA)
    op.drop_constraint(op.f("ck_companies_dv_digit"), TABLE, schema=SCHEMA)
    op.create_check_constraint(
        op.f("ck_companies_check_digit_digit"), TABLE, "check_digit ~ '^[0-9]$'", schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_companies_check_digit_digit"), TABLE, schema=SCHEMA)
    op.alter_column(TABLE, "check_digit", new_column_name="dv", schema=SCHEMA)
    op.create_check_constraint(
        op.f("ck_companies_dv_digit"), TABLE, "dv ~ '^[0-9]$'", schema=SCHEMA
    )
