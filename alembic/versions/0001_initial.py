"""inicial: clientes (sobre public.tenants), responsabilidades, contactos y notas

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-28 18:00:00.000000

Las personas, organizaciones, roles y membresías son de la plataforma (schema public):
esta migración no las crea, solo les apunta con FK. Crear esas FK exige el permiso
REFERENCES sobre public.tenants, public.users y public.memberships.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de la revisión, usados por Alembic.
revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Escrito a mano (no DB_SCHEMA): una migración no debe cambiar si el código cambia después
SCHEMA = "exogena"
PLATFORM = "public"

# Nombre separado como en el RUT (clientes persona natural)
NAME_COLUMNS = ("first_name", "middle_name", "last_name", "second_last_name")


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


def _unique_active(name: str, table: str, columns: list[str], where: str = "NOT is_deleted"):
    """Índice único solo entre filas no borradas (borrado lógico)."""
    op.create_index(
        name, table, columns, unique=True, schema=SCHEMA, postgresql_where=sa.text(where)
    )


def upgrade() -> None:
    # Solo si no existe: en AWS lo crea un administrador y el usuario de la migración no tiene
    # permiso CREATE sobre la base. Postgres revisa ese permiso incluso con IF NOT EXISTS.
    op.execute(
        "DO $$ BEGIN "
        f"IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = '{SCHEMA}') "
        f'THEN CREATE SCHEMA "{SCHEMA}"; '
        "END IF; END $$"
    )

    # ── clients: datos del RUT de un tenant de la plataforma ──
    op.create_table(
        "clients",
        *_base_columns(),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("nit", sa.String(length=15), nullable=False),
        sa.Column("dv", sa.String(length=1), nullable=False),
        sa.Column("person_type", sa.String(length=10), nullable=False),
        sa.Column("legal_name", sa.String(length=250), nullable=True),
        *(sa.Column(column, sa.String(length=100), nullable=True) for column in NAME_COLUMNS),
        sa.Column("address", sa.String(length=250), nullable=True),
        sa.Column("department_code", sa.String(length=2), nullable=True),
        sa.Column("city_code", sa.String(length=5), nullable=True),
        sa.Column("rut_email", sa.String(length=320), nullable=True),
        sa.Column("main_activity_code", sa.String(length=4), nullable=True),
        sa.Column("rut_status", sa.String(length=20), nullable=True),
        sa.Column("rut_updated_at", sa.Date(), nullable=True),
        sa.Column("rut_file_key", sa.String(length=500), nullable=True),
        sa.Column("trade_name", sa.String(length=250), nullable=True),
        sa.CheckConstraint("nit ~ '^[0-9]{5,15}$'", name=op.f("ck_clients_nit_digits")),
        sa.CheckConstraint("dv ~ '^[0-9]$'", name=op.f("ck_clients_dv_digit")),
        sa.CheckConstraint(
            "person_type IN ('natural', 'juridica')", name=op.f("ck_clients_person_type_valid")
        ),
        sa.CheckConstraint(
            "department_code ~ '^[0-9]{2}$'", name=op.f("ck_clients_department_code_dane")
        ),
        sa.CheckConstraint("city_code ~ '^[0-9]{5}$'", name=op.f("ck_clients_city_code_dane")),
        sa.CheckConstraint(
            "main_activity_code ~ '^[0-9]{4}$'", name=op.f("ck_clients_main_activity_code_ciiu")
        ),
        sa.CheckConstraint(
            "(person_type = 'juridica' AND legal_name IS NOT NULL)"
            " OR (person_type = 'natural' AND first_name IS NOT NULL AND last_name IS NOT NULL)",
            name=op.f("ck_clients_name_matches_person_type"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], [f"{PLATFORM}.tenants.id"], name=op.f("fk_clients_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clients")),
        schema=SCHEMA,
    )
    _unique_active("ux_clients_nit", "clients", ["nit"])
    _unique_active("ux_clients_tenant_id", "clients", ["tenant_id"])

    # ── client_tax_responsibilities ──
    op.create_table(
        "client_tax_responsibilities",
        *_base_columns(),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=2), nullable=False),
        sa.CheckConstraint(
            "code ~ '^[0-9]{1,2}$'", name=op.f("ck_client_tax_responsibilities_code_digits")
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            [f"{SCHEMA}.clients.id"],
            name=op.f("fk_client_tax_responsibilities_client_id_clients"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_tax_responsibilities")),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_exogena_client_tax_responsibilities_client_id"),
        "client_tax_responsibilities",
        ["client_id"],
        schema=SCHEMA,
    )
    _unique_active(
        "ux_client_tax_responsibilities_client_code",
        "client_tax_responsibilities",
        ["client_id", "code"],
    )

    # ── client_contacts: cargo, teléfono y contacto principal de cada membresía ──
    op.create_table(
        "client_contacts",
        *_base_columns(),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("is_primary_contact", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["client_id"],
            [f"{SCHEMA}.clients.id"],
            name=op.f("fk_client_contacts_client_id_clients"),
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            [f"{PLATFORM}.memberships.id"],
            name=op.f("fk_client_contacts_membership_id_memberships"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_contacts")),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_exogena_client_contacts_client_id"),
        "client_contacts",
        ["client_id"],
        schema=SCHEMA,
    )
    _unique_active("ux_client_contacts_membership_id", "client_contacts", ["membership_id"])
    _unique_active(
        "ux_client_contacts_primary_contact",
        "client_contacts",
        ["client_id"],
        where="is_primary_contact AND NOT is_deleted",
    )

    # ── notes ──
    op.create_table(
        "notes",
        *_base_columns(),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], [f"{PLATFORM}.users.id"], name=op.f("fk_notes_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notes")),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_exogena_notes_title"), "notes", ["title"], schema=SCHEMA)
    op.create_index(op.f("ix_exogena_notes_user_id"), "notes", ["user_id"], schema=SCHEMA)

    # ── Permisos: la app corre como wiseerp_app (y wiseerp_ro solo lee), igual que en public.
    # Las tablas de futuras migraciones reciben los mismos permisos (DEFAULT PRIVILEGES).
    op.execute(
        f"""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'wiseerp_app') THEN
                GRANT USAGE ON SCHEMA "{SCHEMA}" TO wiseerp_app;
                GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "{SCHEMA}"
                    TO wiseerp_app;
                ALTER DEFAULT PRIVILEGES IN SCHEMA "{SCHEMA}"
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO wiseerp_app;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'wiseerp_ro') THEN
                GRANT USAGE ON SCHEMA "{SCHEMA}" TO wiseerp_ro;
                GRANT SELECT ON ALL TABLES IN SCHEMA "{SCHEMA}" TO wiseerp_ro;
                ALTER DEFAULT PRIVILEGES IN SCHEMA "{SCHEMA}" GRANT SELECT ON TABLES TO wiseerp_ro;
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    for table in ("notes", "client_contacts", "client_tax_responsibilities", "clients"):
        op.drop_table(table, schema=SCHEMA)
    # El schema no se borra: en AWS lo crea un administrador y habría que pedirlo de nuevo
