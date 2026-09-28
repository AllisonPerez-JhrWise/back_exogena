"""inicial: usuarios, roles, identidades, clientes y notas en el schema exogena

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-28 12:00:00.000000

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

ROLES = [
    ("admin", "Administrador", "Puede crear clientes y administrar usuarios"),
    ("colaborador", "Colaborador", "Personal de la firma"),
    ("usuario_cliente", "Usuario de cliente", "Persona de una empresa cliente"),
]

# Nombre separado como en los documentos colombianos (usuarios y clientes persona natural)
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

    # ── users ──
    op.create_table(
        "users",
        *_base_columns(),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("middle_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("second_last_name", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("can_login", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lowercase")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        schema=SCHEMA,
    )
    _unique_active("ux_users_email", "users", ["email"])

    # ── roles + roles iniciales ──
    op.create_table(
        "roles",
        *_base_columns(),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("code", name=op.f("uq_roles_code")),
        schema=SCHEMA,
    )
    for code, name, description in ROLES:
        op.execute(
            sa.text(
                f"INSERT INTO {SCHEMA}.roles "
                "(id, is_deleted, is_active, created_at, code, name, description) "
                "VALUES (gen_random_uuid(), false, true, now(), :code, :name, :description)"
            ).bindparams(code=code, name=name, description=description)
        )

    # ── user_roles ──
    op.create_table(
        "user_roles",
        *_base_columns(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], [f"{SCHEMA}.users.id"], name=op.f("fk_user_roles_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], [f"{SCHEMA}.roles.id"], name=op.f("fk_user_roles_role_id_roles")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_roles")),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_exogena_user_roles_user_id"), "user_roles", ["user_id"], schema=SCHEMA
    )
    op.create_index(
        op.f("ix_exogena_user_roles_role_id"), "user_roles", ["role_id"], schema=SCHEMA
    )
    _unique_active("ux_user_roles_user_role", "user_roles", ["user_id", "role_id"])

    # ── user_identities ──
    op.create_table(
        "user_identities",
        *_base_columns(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.CheckConstraint(
            "provider IN ('password', 'google', 'microsoft')",
            name=op.f("ck_user_identities_provider_valid"),
        ),
        sa.CheckConstraint(
            "(provider = 'password') = (password_hash IS NOT NULL)",
            name=op.f("ck_user_identities_password_hash_only_for_password"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], [f"{SCHEMA}.users.id"], name=op.f("fk_user_identities_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_identities")),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_exogena_user_identities_user_id"), "user_identities", ["user_id"], schema=SCHEMA
    )
    _unique_active(
        "ux_user_identities_provider_subject", "user_identities", ["provider", "subject"]
    )

    # ── clients ──
    op.create_table(
        "clients",
        *_base_columns(),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clients")),
        schema=SCHEMA,
    )
    _unique_active("ux_clients_nit", "clients", ["nit"])

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

    # ── client_users ──
    op.create_table(
        "client_users",
        *_base_columns(),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.String(length=100), nullable=True),
        sa.Column("is_primary_contact", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["client_id"], [f"{SCHEMA}.clients.id"], name=op.f("fk_client_users_client_id_clients")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], [f"{SCHEMA}.users.id"], name=op.f("fk_client_users_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_users")),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_exogena_client_users_client_id"), "client_users", ["client_id"], schema=SCHEMA
    )
    op.create_index(
        op.f("ix_exogena_client_users_user_id"), "client_users", ["user_id"], schema=SCHEMA
    )
    _unique_active("ux_client_users_client_user", "client_users", ["client_id", "user_id"])
    _unique_active(
        "ux_client_users_primary_contact",
        "client_users",
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notes")),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_exogena_notes_title"), "notes", ["title"], schema=SCHEMA)
    op.create_index(op.f("ix_exogena_notes_user_id"), "notes", ["user_id"], schema=SCHEMA)


def downgrade() -> None:
    for table in (
        "notes",
        "client_users",
        "client_tax_responsibilities",
        "clients",
        "user_identities",
        "user_roles",
        "roles",
        "users",
    ):
        op.drop_table(table, schema=SCHEMA)
    # El schema no se borra: en AWS lo crea un administrador y habría que pedirlo de nuevo
