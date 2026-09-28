"""catálogo: obligaciones, tipos de servicio y servicios

Revision ID: 0002_catalog
Revises: 0001_initial
Create Date: 2026-09-28 20:00:00.000000

Los permisos para wiseerp_app y wiseerp_ro los dan los DEFAULT PRIVILEGES de la 0001.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de la revisión, usados por Alembic.
revision: str = "0002_catalog"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "exogena"
PLATFORM = "public"


def _base_columns() -> list[sa.Column]:
    """Columnas que tiene toda BaseTable."""
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
    ]


def _tenant_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id"], [f"{PLATFORM}.tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants")
    )


def _named_catalog_table(table: str, *extra: sa.Column | sa.Constraint) -> None:
    """Obligaciones y tipos de servicio: nombre único por organización (sin mayúsculas)."""
    op.create_table(
        table,
        *_base_columns(),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        *extra,
        sa.Column("inactivation_reason", sa.String(length=500), nullable=True),
        _tenant_fk(table),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        schema=SCHEMA,
    )
    op.create_index(op.f(f"ix_exogena_{table}_tenant_id"), table, ["tenant_id"], schema=SCHEMA)
    op.create_index(
        f"ux_{table}_tenant_name",
        table,
        ["tenant_id", sa.text("lower(name)")],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("NOT is_deleted"),
    )


def upgrade() -> None:
    _named_catalog_table(
        "obligations",
        sa.Column("nature", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "nature IN ('tributaria', 'servicio_recurrente')",
            name=op.f("ck_obligations_nature_valid"),
        ),
    )
    _named_catalog_table("service_types")

    op.create_table(
        "services",
        *_base_columns(),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("obligation_id", sa.Uuid(), nullable=False),
        sa.Column("service_type_id", sa.Uuid(), nullable=False),
        sa.Column("inactivation_reason", sa.String(length=500), nullable=True),
        _tenant_fk("services"),
        sa.ForeignKeyConstraint(
            ["obligation_id"],
            [f"{SCHEMA}.obligations.id"],
            name=op.f("fk_services_obligation_id_obligations"),
        ),
        sa.ForeignKeyConstraint(
            ["service_type_id"],
            [f"{SCHEMA}.service_types.id"],
            name=op.f("fk_services_service_type_id_service_types"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_services")),
        schema=SCHEMA,
    )
    for column in ("tenant_id", "obligation_id", "service_type_id"):
        op.create_index(
            op.f(f"ix_exogena_services_{column}"), "services", [column], schema=SCHEMA
        )
    op.create_index(
        "ux_services_tenant_obligation_type",
        "services",
        ["tenant_id", "obligation_id", "service_type_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("NOT is_deleted"),
    )


def downgrade() -> None:
    for table in ("services", "service_types", "obligations"):
        op.drop_table(table, schema=SCHEMA)
