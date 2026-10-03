"""empresas: el NIT tiene de 6 a 10 dígitos, como en todos los servicios

Revision ID: 0009_nit_six_to_ten_digits
Revises: 0008_rut_boxes_and_formats
Create Date: 2026-10-03

La misma regla de wise_comun.nit (identidad y extracción): solo dígitos, de 6 a 10, sin
el de verificación. Antes se aceptaban de 5 a 15.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009_nit_six_to_ten_digits"
down_revision: str | Sequence[str] | None = "0008_rut_boxes_and_formats"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "exogena"
TABLE = "companies"
NAME = "ck_companies_nit_digits"


def upgrade() -> None:
    op.drop_constraint(op.f(NAME), TABLE, schema=SCHEMA)
    op.create_check_constraint(op.f(NAME), TABLE, "nit ~ '^[0-9]{6,10}$'", schema=SCHEMA)


def downgrade() -> None:
    op.drop_constraint(op.f(NAME), TABLE, schema=SCHEMA)
    op.create_check_constraint(op.f(NAME), TABLE, "nit ~ '^[0-9]{5,15}$'", schema=SCHEMA)
