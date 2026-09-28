"""inicial: accounts.users, notes.notes

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-27 23:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

# identificadores de la revisión, usados por Alembic.
revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    op.execute('CREATE SCHEMA IF NOT EXISTS "accounts"')
    op.execute('CREATE SCHEMA IF NOT EXISTS "notes"')

    op.create_table(
        "users",
        *_base_columns(),
        sa.Column("email", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("username", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("full_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("hashed_password", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("google_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("avatar_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        schema="accounts",
    )
    op.create_index(
        op.f("ix_accounts_users_email"), "users", ["email"], unique=True, schema="accounts"
    )
    op.create_index(
        op.f("ix_accounts_users_username"), "users", ["username"], unique=True, schema="accounts"
    )
    op.create_index(
        op.f("ix_accounts_users_google_id"), "users", ["google_id"], unique=False, schema="accounts"
    )

    op.create_table(
        "notes",
        *_base_columns(),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("content", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notes")),
        schema="notes",
    )
    op.create_index(op.f("ix_notes_notes_title"), "notes", ["title"], unique=False, schema="notes")
    op.create_index(
        op.f("ix_notes_notes_user_id"), "notes", ["user_id"], unique=False, schema="notes"
    )


def downgrade() -> None:
    op.drop_table("notes", schema="notes")
    op.drop_table("users", schema="accounts")
    op.execute('DROP SCHEMA IF EXISTS "notes"')
    op.execute('DROP SCHEMA IF EXISTS "accounts"')
