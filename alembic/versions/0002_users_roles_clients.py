"""usuarios, roles, identidades y clientes

Revision ID: 0002_users_roles_clients
Revises: 0001_initial
Create Date: 2026-09-28 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de la revisión, usados por Alembic.
revision: str = "0002_users_roles_clients"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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


def upgrade() -> None:
    # ── accounts.roles + roles iniciales ──
    op.create_table(
        "roles",
        *_base_columns(),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("code", name=op.f("uq_roles_code")),
        schema="accounts",
    )
    for code, name, description in ROLES:
        op.execute(
            sa.text(
                "INSERT INTO accounts.roles (id, is_deleted, is_active, created_at, code, name, description) "
                "VALUES (gen_random_uuid(), false, true, now(), :code, :name, :description)"
            ).bindparams(code=code, name=name, description=description)
        )

    # ── accounts.user_identities: la contraseña y Google salen de users ──
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
            ["user_id"], ["accounts.users.id"], name=op.f("fk_user_identities_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_identities")),
        schema="accounts",
    )
    op.create_index(
        op.f("ix_accounts_user_identities_user_id"),
        "user_identities",
        ["user_id"],
        schema="accounts",
    )
    op.create_index(
        "ux_user_identities_provider_subject",
        "user_identities",
        ["provider", "subject"],
        unique=True,
        schema="accounts",
        postgresql_where=sa.text("NOT is_deleted"),
    )
    # Los usuarios existentes conservan su forma de entrar
    op.execute(
        "INSERT INTO accounts.user_identities "
        "(id, is_deleted, is_active, created_at, user_id, provider, subject, password_hash) "
        "SELECT gen_random_uuid(), false, true, now(), id, 'password', lower(email), hashed_password "
        "FROM accounts.users WHERE hashed_password IS NOT NULL"
    )
    op.execute(
        "INSERT INTO accounts.user_identities "
        "(id, is_deleted, is_active, created_at, user_id, provider, subject) "
        "SELECT gen_random_uuid(), false, true, now(), id, 'google', google_id "
        "FROM accounts.users WHERE google_id IS NOT NULL"
    )

    # ── accounts.users ──
    op.drop_index("ix_accounts_users_username", table_name="users", schema="accounts")
    op.drop_index("ix_accounts_users_google_id", table_name="users", schema="accounts")
    op.drop_index("ix_accounts_users_email", table_name="users", schema="accounts")
    op.drop_column("users", "username", schema="accounts")
    op.drop_column("users", "hashed_password", schema="accounts")
    op.drop_column("users", "google_id", schema="accounts")

    op.execute("UPDATE accounts.users SET email = lower(email)")
    op.alter_column(
        "users", "email", type_=sa.String(length=320), existing_nullable=False, schema="accounts"
    )
    # El nombre se separa: primera palabra -> primer nombre, el resto -> primer apellido
    for column in NAME_COLUMNS:
        op.add_column(
            "users", sa.Column(column, sa.String(length=100), nullable=True), schema="accounts"
        )
    op.execute(
        "UPDATE accounts.users SET "
        "first_name = split_part(coalesce(nullif(trim(full_name), ''), split_part(email, '@', 1)), ' ', 1), "
        "last_name = CASE WHEN position(' ' in trim(coalesce(full_name, ''))) > 0 "
        "THEN trim(substring(trim(full_name) from position(' ' in trim(full_name)) + 1)) "
        "ELSE '' END"
    )
    op.alter_column("users", "first_name", nullable=False, schema="accounts")
    op.alter_column("users", "last_name", nullable=False, schema="accounts")
    op.drop_column("users", "full_name", schema="accounts")
    op.add_column("users", sa.Column("phone", sa.String(length=30), nullable=True), schema="accounts")
    # Los usuarios que ya existían podían entrar: conservan el acceso
    op.add_column(
        "users",
        sa.Column("can_login", sa.Boolean(), nullable=False, server_default=sa.true()),
        schema="accounts",
    )
    op.alter_column("users", "can_login", server_default=None, schema="accounts")
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        schema="accounts",
    )
    op.create_check_constraint(
        op.f("ck_users_email_lowercase"), "users", "email = lower(email)", schema="accounts"
    )
    op.create_index(
        "ux_users_email",
        "users",
        ["email"],
        unique=True,
        schema="accounts",
        postgresql_where=sa.text("NOT is_deleted"),
    )

    # ── accounts.user_roles ──
    op.create_table(
        "user_roles",
        *_base_columns(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["accounts.users.id"], name=op.f("fk_user_roles_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["accounts.roles.id"], name=op.f("fk_user_roles_role_id_roles")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_roles")),
        schema="accounts",
    )
    op.create_index(
        op.f("ix_accounts_user_roles_user_id"), "user_roles", ["user_id"], schema="accounts"
    )
    op.create_index(
        op.f("ix_accounts_user_roles_role_id"), "user_roles", ["role_id"], schema="accounts"
    )
    op.create_index(
        "ux_user_roles_user_role",
        "user_roles",
        ["user_id", "role_id"],
        unique=True,
        schema="accounts",
        postgresql_where=sa.text("NOT is_deleted"),
    )

    # ── clients ──
    op.execute('CREATE SCHEMA IF NOT EXISTS "clients"')
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
        schema="clients",
    )
    op.create_index(
        "ux_clients_nit",
        "clients",
        ["nit"],
        unique=True,
        schema="clients",
        postgresql_where=sa.text("NOT is_deleted"),
    )

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
            ["clients.clients.id"],
            name=op.f("fk_client_tax_responsibilities_client_id_clients"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_tax_responsibilities")),
        schema="clients",
    )
    op.create_index(
        op.f("ix_clients_client_tax_responsibilities_client_id"),
        "client_tax_responsibilities",
        ["client_id"],
        schema="clients",
    )
    op.create_index(
        "ux_client_tax_responsibilities_client_code",
        "client_tax_responsibilities",
        ["client_id", "code"],
        unique=True,
        schema="clients",
        postgresql_where=sa.text("NOT is_deleted"),
    )

    op.create_table(
        "client_users",
        *_base_columns(),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.String(length=100), nullable=True),
        sa.Column("is_primary_contact", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["client_id"], ["clients.clients.id"], name=op.f("fk_client_users_client_id_clients")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["accounts.users.id"], name=op.f("fk_client_users_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_users")),
        schema="clients",
    )
    op.create_index(
        op.f("ix_clients_client_users_client_id"), "client_users", ["client_id"], schema="clients"
    )
    op.create_index(
        op.f("ix_clients_client_users_user_id"), "client_users", ["user_id"], schema="clients"
    )
    op.create_index(
        "ux_client_users_client_user",
        "client_users",
        ["client_id", "user_id"],
        unique=True,
        schema="clients",
        postgresql_where=sa.text("NOT is_deleted"),
    )
    op.create_index(
        "ux_client_users_primary_contact",
        "client_users",
        ["client_id"],
        unique=True,
        schema="clients",
        postgresql_where=sa.text("is_primary_contact AND NOT is_deleted"),
    )


def downgrade() -> None:
    # ── clients ──
    op.drop_table("client_users", schema="clients")
    op.drop_table("client_tax_responsibilities", schema="clients")
    op.drop_table("clients", schema="clients")
    op.execute('DROP SCHEMA IF EXISTS "clients"')

    # ── accounts: se devuelven las columnas de users desde las identidades ──
    op.drop_table("user_roles", schema="accounts")

    op.drop_index("ux_users_email", table_name="users", schema="accounts")
    op.drop_constraint(op.f("ck_users_email_lowercase"), "users", schema="accounts")
    op.drop_column("users", "last_login_at", schema="accounts")
    op.drop_column("users", "can_login", schema="accounts")
    op.drop_column("users", "phone", schema="accounts")
    op.add_column("users", sa.Column("full_name", sa.String(), nullable=True), schema="accounts")
    op.execute(
        "UPDATE accounts.users SET full_name = concat_ws(' ', "
        "nullif(first_name, ''), middle_name, nullif(last_name, ''), second_last_name)"
    )
    for column in NAME_COLUMNS:
        op.drop_column("users", column, schema="accounts")
    op.alter_column("users", "email", type_=sa.String(), existing_nullable=False, schema="accounts")
    op.add_column("users", sa.Column("google_id", sa.String(), nullable=True), schema="accounts")
    op.add_column("users", sa.Column("hashed_password", sa.String(), nullable=True), schema="accounts")
    op.add_column("users", sa.Column("username", sa.String(), nullable=True), schema="accounts")
    op.execute(
        "UPDATE accounts.users u SET hashed_password = i.password_hash "
        "FROM accounts.user_identities i "
        "WHERE i.user_id = u.id AND i.provider = 'password' AND NOT i.is_deleted"
    )
    op.execute(
        "UPDATE accounts.users u SET google_id = i.subject "
        "FROM accounts.user_identities i "
        "WHERE i.user_id = u.id AND i.provider = 'google' AND NOT i.is_deleted"
    )
    op.create_index("ix_accounts_users_email", "users", ["email"], unique=True, schema="accounts")
    op.create_index("ix_accounts_users_google_id", "users", ["google_id"], schema="accounts")
    op.create_index(
        "ix_accounts_users_username", "users", ["username"], unique=True, schema="accounts"
    )

    op.drop_table("user_identities", schema="accounts")
    op.drop_table("roles", schema="accounts")
