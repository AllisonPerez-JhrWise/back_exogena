"""clientes: notas opcionales (paso 2 del formulario "Nuevo cliente")

Revision ID: 0003_client_notes
Revises: 0002_catalog
Create Date: 2026-09-28 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de la revisión, usados por Alembic.
revision: str = "0003_client_notes"
down_revision: str | Sequence[str] | None = "0002_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "exogena"


def upgrade() -> None:
    op.add_column(
        "clients", sa.Column("notes", sa.String(length=2000), nullable=True), schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_column("clients", "notes", schema=SCHEMA)
