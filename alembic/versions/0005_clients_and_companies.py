"""clientes y empresas: el cliente (grupo) es la cuenta en la plataforma y la empresa es
cada NIT, con sus versiones del RUT. Los compromisos pasan a ser de la empresa.

Revision ID: 0005_clients_and_companies
Revises: 0004_engagements
Create Date: 2026-09-29 10:00:00.000000

Borra y vuelve a crear las tablas de clientes y compromisos: al escribirla estaban vacías
en todos los ambientes. NO tiene downgrade (ver downgrade()).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de la revisión, usados por Alembic.
revision: str = "0005_clients_and_companies"
down_revision: str | Sequence[str] | None = "0004_engagements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "exogena"
PLATFORM = "public"
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


def _fk(table: str, column: str, target: str) -> sa.ForeignKeyConstraint:
    referred = target.split(".")[1]
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=op.f(f"fk_{table}_{column}_{referred}")
    )


def _contact_columns() -> list[sa.Column]:
    return [
        sa.Column("contact_name", sa.String(length=200), nullable=True),
        sa.Column("contact_email", sa.String(length=320), nullable=True),
        sa.Column("contact_phone", sa.String(length=30), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
    ]


def _index(table: str, column: str) -> None:
    op.create_index(op.f(f"ix_exogena_{table}_{column}"), table, [column], schema=SCHEMA)


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
    for table in ("engagements", "client_contacts", "client_tax_responsibilities", "clients"):
        op.drop_table(table, schema=SCHEMA)

    # ── clients: el cliente o grupo, 1 a 1 con su cuenta (tenant) en la plataforma ──
    op.create_table(
        "clients",
        *_base_columns(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=False),
        *_contact_columns(),
        sa.Column("inactivation_reason", sa.String(length=500), nullable=True),
        _fk("clients", "organization_id", f"{PLATFORM}.tenants"),
        _fk("clients", "tenant_id", f"{PLATFORM}.tenants"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clients")),
        schema=SCHEMA,
    )
    _index("clients", "organization_id")
    _unique_active("ux_clients_tenant_id", "clients", ["tenant_id"])

    # ── companies: una por NIT, con los datos del RUT vigente ──
    op.create_table(
        "companies",
        *_base_columns(),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("trade_name", sa.String(length=250), nullable=True),
        *_contact_columns(),
        sa.Column("nit", sa.String(length=15), nullable=False),
        sa.Column("dv", sa.String(length=1), nullable=False),
        sa.Column("person_type", sa.String(length=10), nullable=False),
        sa.Column("taxpayer_type", sa.String(length=100), nullable=True),
        sa.Column("legal_name", sa.String(length=250), nullable=True),
        *(sa.Column(column, sa.String(length=100), nullable=True) for column in NAME_COLUMNS),
        sa.Column("address", sa.String(length=250), nullable=True),
        sa.Column("department_code", sa.String(length=2), nullable=True),
        sa.Column("city_code", sa.String(length=5), nullable=True),
        sa.Column("rut_email", sa.String(length=320), nullable=True),
        sa.Column("rut_phone", sa.String(length=30), nullable=True),
        sa.Column("main_activity_code", sa.String(length=4), nullable=True),
        sa.Column("rut_status", sa.String(length=20), nullable=True),
        sa.Column("rut_generated_at", sa.Date(), nullable=True),
        sa.Column("rut_updated_at", sa.Date(), nullable=True),
        sa.Column("inactivation_reason", sa.String(length=500), nullable=True),
        sa.CheckConstraint("nit ~ '^[0-9]{5,15}$'", name=op.f("ck_companies_nit_digits")),
        sa.CheckConstraint("dv ~ '^[0-9]$'", name=op.f("ck_companies_dv_digit")),
        sa.CheckConstraint(
            "person_type IN ('natural', 'juridica')", name=op.f("ck_companies_person_type_valid")
        ),
        sa.CheckConstraint(
            "department_code ~ '^[0-9]{2}$'", name=op.f("ck_companies_department_code_dane")
        ),
        sa.CheckConstraint("city_code ~ '^[0-9]{5}$'", name=op.f("ck_companies_city_code_dane")),
        sa.CheckConstraint(
            "main_activity_code ~ '^[0-9]{4}$'",
            name=op.f("ck_companies_main_activity_code_ciiu"),
        ),
        sa.CheckConstraint(
            "(person_type = 'juridica' AND legal_name IS NOT NULL)"
            " OR (person_type = 'natural' AND first_name IS NOT NULL AND last_name IS NOT NULL)",
            name=op.f("ck_companies_name_matches_person_type"),
        ),
        _fk("companies", "client_id", f"{SCHEMA}.clients"),
        _fk("companies", "organization_id", f"{PLATFORM}.tenants"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
        schema=SCHEMA,
    )
    _index("companies", "client_id")
    _index("companies", "organization_id")
    _unique_active("ux_companies_organization_nit", "companies", ["organization_id", "nit"])

    op.create_table(
        "company_tax_responsibilities",
        *_base_columns(),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=2), nullable=False),
        sa.CheckConstraint(
            "code ~ '^[0-9]{1,2}$'", name=op.f("ck_company_tax_responsibilities_code_digits")
        ),
        _fk("company_tax_responsibilities", "company_id", f"{SCHEMA}.companies"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_tax_responsibilities")),
        schema=SCHEMA,
    )
    _index("company_tax_responsibilities", "company_id")
    _unique_active(
        "ux_company_tax_responsibilities_company_code",
        "company_tax_responsibilities",
        ["company_id", "code"],
    )

    op.create_table(
        "company_rut_versions",
        *_base_columns(),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("generated_at", sa.Date(), nullable=True),
        sa.Column("rut_updated_at", sa.Date(), nullable=True),
        sa.Column("covers_tax_year", sa.Integer(), nullable=True),
        sa.Column("is_historical", sa.Boolean(), nullable=False),
        sa.Column("extraction_id", sa.Uuid(), nullable=True),
        sa.Column("file_key", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "covers_tax_year BETWEEN 1990 AND 2100",
            name=op.f("ck_company_rut_versions_covers_tax_year_range"),
        ),
        _fk("company_rut_versions", "company_id", f"{SCHEMA}.companies"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_rut_versions")),
        schema=SCHEMA,
    )
    _index("company_rut_versions", "company_id")

    # ── client_members: cargo y celular de cada persona con acceso al cliente ──
    op.create_table(
        "client_members",
        *_base_columns(),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        _fk("client_members", "client_id", f"{SCHEMA}.clients"),
        _fk("client_members", "membership_id", f"{PLATFORM}.memberships"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_members")),
        schema=SCHEMA,
    )
    _index("client_members", "client_id")
    _unique_active("ux_client_members_membership_id", "client_members", ["membership_id"])

    # ── engagements: ahora de la empresa ──
    op.create_table(
        "engagements",
        *_base_columns(),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
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
        _fk("engagements", "tenant_id", f"{PLATFORM}.tenants"),
        _fk("engagements", "company_id", f"{SCHEMA}.companies"),
        _fk("engagements", "service_id", f"{SCHEMA}.services"),
        _fk("engagements", "obligation_id", f"{SCHEMA}.obligations"),
        _fk("engagements", "service_type_id", f"{SCHEMA}.service_types"),
        _fk("engagements", "partner_user_id", f"{PLATFORM}.users"),
        _fk("engagements", "manager_user_id", f"{PLATFORM}.users"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_engagements")),
        schema=SCHEMA,
    )
    for column in ("tenant_id", "company_id", "service_id"):
        _index("engagements", column)
    # REGLA DE NEGOCIO: una empresa no tiene dos compromisos del mismo servicio para el
    # mismo año gravable. Si cambia, crear una migración que borre este índice.
    _unique_active(
        "ux_engagements_company_service_year",
        "engagements",
        ["company_id", "service_id", "fiscal_year"],
    )


def downgrade() -> None:
    # Cambio de modelo sin vuelta atrás automática: las tablas anteriores guardaban la
    # empresa como "cliente". Para volver, recrear la base de datos local (make reset).
    raise NotImplementedError("0005_clients_and_companies has no downgrade")
