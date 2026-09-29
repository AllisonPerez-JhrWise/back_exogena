"""grupos como catálogo: la empresa es el cliente y el grupo es opcional

Revision ID: 0007_groups_catalog
Revises: 0006_clients_are_not_tenants
Create Date: 2026-09-29 18:00:00.000000

- groups: catálogo de grupos de la firma (solo el nombre). No se repite, aunque se escriba
  con otras mayúsculas, tildes o espacios (name_key).
- companies.group_id reemplaza a companies.client_id; se retira la tabla clients.
- company_users reemplaza a client_users: el usuario del cliente ve solo su empresa.

Sin datos que conservar al escribirla (ningún ambiente la tenía con información real).
NO tiene downgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de la revisión, usados por Alembic.
revision: str = "0007_groups_catalog"
down_revision: str | Sequence[str] | None = "0006_clients_are_not_tenants"
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


def _unique_active(name: str, table: str, columns: list[str]) -> None:
    op.create_index(
        name,
        table,
        columns,
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("NOT is_deleted"),
    )


def upgrade() -> None:
    # ── groups ──
    op.create_table(
        "groups",
        *_base_columns(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("name_key", sa.String(length=250), nullable=False),
        sa.Column("inactivation_reason", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            [f"{PLATFORM}.tenants.id"],
            name=op.f("fk_groups_organization_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_groups")),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_exogena_groups_organization_id"), "groups", ["organization_id"], schema=SCHEMA
    )
    _unique_active("ux_groups_organization_name_key", "groups", ["organization_id", "name_key"])

    # ── Fuera clients y client_users ──
    op.drop_table("client_users", schema=SCHEMA)
    op.drop_index(op.f("ix_exogena_companies_client_id"), table_name="companies", schema=SCHEMA)
    op.drop_constraint(
        op.f("fk_companies_client_id_clients"), "companies", type_="foreignkey", schema=SCHEMA
    )
    op.drop_column("companies", "client_id", schema=SCHEMA)
    op.drop_table("clients", schema=SCHEMA)

    # ── companies.group_id (opcional) ──
    op.add_column("companies", sa.Column("group_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.create_foreign_key(
        op.f("fk_companies_group_id_groups"),
        "companies",
        "groups",
        ["group_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_exogena_companies_group_id"), "companies", ["group_id"], schema=SCHEMA
    )

    # ── company_users: el usuario del cliente ve solo su empresa ──
    op.create_table(
        "company_users",
        *_base_columns(),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("position", sa.String(length=100), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "email = lower(email)", name=op.f("ck_company_users_email_lowercase")
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            [f"{SCHEMA}.companies.id"],
            name=op.f("fk_company_users_company_id_companies"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], [f"{PLATFORM}.users.id"], name=op.f("fk_company_users_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_users")),
        schema=SCHEMA,
    )
    for column in ("company_id", "user_id"):
        op.create_index(
            op.f(f"ix_exogena_company_users_{column}"), "company_users", [column], schema=SCHEMA
        )
    _unique_active("ux_company_users_company_email", "company_users", ["company_id", "email"])


def downgrade() -> None:
    raise NotImplementedError("0007_groups_catalog has no downgrade")
