"""compromisos: servicio de un cliente para un año gravable, con socio y gerente

Revision ID: 0004_engagements
Revises: 0003_client_notes
Create Date: 2026-09-28 23:00:00.000000

Los permisos para wiseerp_app y wiseerp_ro los dan los DEFAULT PRIVILEGES de la 0001.
Las FK a public.users exigen el permiso REFERENCES (ya pedido para la 0001).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de la revisión, usados por Alembic.
revision: str = "0004_engagements"
down_revision: str | Sequence[str] | None = "0003_client_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "exogena"
PLATFORM = "public"


def _fk(column: str, target: str) -> sa.ForeignKeyConstraint:
    table = target.split(".")[1]
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=op.f(f"fk_engagements_{column}_{table}")
    )


def upgrade() -> None:
    op.create_table(
        "engagements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("obligation_id", sa.Uuid(), nullable=False),
        sa.Column("service_type_id", sa.Uuid(), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("partner_user_id", sa.Uuid(), nullable=False),
        sa.Column("manager_user_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "fiscal_year BETWEEN 2000 AND 2100", name=op.f("ck_engagements_fiscal_year_range")
        ),
        sa.CheckConstraint(
            "status IN ('por_iniciar', 'en_curso', 'cerrado')",
            name=op.f("ck_engagements_status_valid"),
        ),
        _fk("tenant_id", f"{PLATFORM}.tenants"),
        _fk("client_id", f"{SCHEMA}.clients"),
        _fk("service_id", f"{SCHEMA}.services"),
        _fk("obligation_id", f"{SCHEMA}.obligations"),
        _fk("service_type_id", f"{SCHEMA}.service_types"),
        _fk("partner_user_id", f"{PLATFORM}.users"),
        _fk("manager_user_id", f"{PLATFORM}.users"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_engagements")),
        schema=SCHEMA,
    )
    for column in ("tenant_id", "client_id", "service_id"):
        op.create_index(
            op.f(f"ix_exogena_engagements_{column}"), "engagements", [column], schema=SCHEMA
        )
    # REGLA DE NEGOCIO: un cliente no tiene dos compromisos del mismo servicio para el
    # mismo año gravable. Si cambia, crear una migración que borre este índice.
    op.create_index(
        "ux_engagements_client_service_year",
        "engagements",
        ["client_id", "service_id", "fiscal_year"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("NOT is_deleted"),
    )


def downgrade() -> None:
    op.drop_table("engagements", schema=SCHEMA)
