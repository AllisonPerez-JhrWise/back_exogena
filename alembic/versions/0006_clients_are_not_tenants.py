"""los clientes no son tenants: son registros de la firma; usuarios del cliente como
asignación persona ↔ cliente

Revision ID: 0006_clients_are_not_tenants
Revises: 0005_clients_and_companies
Create Date: 2026-09-29 16:00:00.000000

Confirmado con el equipo de plataforma: tenant = organización = la firma. Los usuarios del
cliente tienen su acceso en la firma (lo crea la plataforma con POST /tenant/miembros);
aquí se guarda a qué cliente están asignados, con su cargo y celular.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de la revisión, usados por Alembic.
revision: str = "0006_clients_are_not_tenants"
down_revision: str | Sequence[str] | None = "0005_clients_and_companies"
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


def upgrade() -> None:
    op.drop_index("ux_clients_tenant_id", table_name="clients", schema=SCHEMA)
    op.drop_constraint(
        op.f("fk_clients_tenant_id_tenants"), "clients", type_="foreignkey", schema=SCHEMA
    )
    op.drop_column("clients", "tenant_id", schema=SCHEMA)
    op.drop_table("client_members", schema=SCHEMA)

    op.create_table(
        "client_users",
        *_base_columns(),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("position", sa.String(length=100), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_client_users_email_lowercase")),
        sa.ForeignKeyConstraint(
            ["client_id"], [f"{SCHEMA}.clients.id"], name=op.f("fk_client_users_client_id_clients")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], [f"{PLATFORM}.users.id"], name=op.f("fk_client_users_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_users")),
        schema=SCHEMA,
    )
    for column in ("client_id", "user_id"):
        op.create_index(
            op.f(f"ix_exogena_client_users_{column}"), "client_users", [column], schema=SCHEMA
        )
    op.create_index(
        "ux_client_users_client_email",
        "client_users",
        ["client_id", "email"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("NOT is_deleted"),
    )


def downgrade() -> None:
    op.drop_table("client_users", schema=SCHEMA)
    op.create_table(
        "client_members",
        *_base_columns(),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.ForeignKeyConstraint(
            ["client_id"], [f"{SCHEMA}.clients.id"], name=op.f("fk_client_members_client_id_clients")
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            [f"{PLATFORM}.memberships.id"],
            name=op.f("fk_client_members_membership_id_memberships"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_members")),
        schema=SCHEMA,
    )
    # Sin datos para reconstruirla: queda vacía (nullable)
    op.add_column("clients", sa.Column("tenant_id", sa.Uuid(), nullable=True), schema=SCHEMA)
