"""inicial: registro de clientes (grupos, empresas con su RUT, usuarios del cliente),
catálogo de obligaciones y servicios, y compromisos

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-29 19:31:23.694814

Todo en el schema exogena. Los IDs de Identidad (la firma, las personas) se guardan sin
FK: el schema de identidad no es de este servicio, como en los demás servicios de la
plataforma. Las FK solo van entre tablas de este servicio.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# identificadores de la revisión, usados por Alembic.
revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Escrito a mano (no DB_SCHEMA): una migración no debe cambiar si el código cambia después
SCHEMA = "exogena"
# Del más dependiente al menos: el orden para borrar
TABLES = (
    "engagements",
    "company_users",
    "company_tax_responsibilities",
    "company_rut_versions",
    "services",
    "companies",
    "service_types",
    "obligations",
    "groups",
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

    op.create_table('groups',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=250), nullable=False),
    sa.Column('name_key', sqlmodel.sql.sqltypes.AutoString(length=250), nullable=False),
    sa.Column('inactivation_reason', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_groups')),
    schema='exogena'
    )
    op.create_index(op.f('ix_exogena_groups_organization_id'), 'groups', ['organization_id'], unique=False, schema='exogena')
    op.create_index('ux_groups_organization_name_key', 'groups', ['organization_id', 'name_key'], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.create_table('obligations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=150), nullable=False),
    sa.Column('description', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    sa.Column('nature', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
    sa.Column('inactivation_reason', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    sa.CheckConstraint("nature IN ('tributaria', 'servicio_recurrente')", name=op.f('ck_obligations_nature_valid')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_obligations')),
    schema='exogena'
    )
    op.create_index(op.f('ix_exogena_obligations_tenant_id'), 'obligations', ['tenant_id'], unique=False, schema='exogena')
    op.create_index('ux_obligations_tenant_name', 'obligations', ['tenant_id', sa.literal_column('lower(name)')], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.create_table('service_types',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=150), nullable=False),
    sa.Column('description', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    sa.Column('inactivation_reason', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_service_types')),
    schema='exogena'
    )
    op.create_index(op.f('ix_exogena_service_types_tenant_id'), 'service_types', ['tenant_id'], unique=False, schema='exogena')
    op.create_index('ux_service_types_tenant_name', 'service_types', ['tenant_id', sa.literal_column('lower(name)')], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.create_table('companies',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('group_id', sa.Uuid(), nullable=True),
    sa.Column('trade_name', sqlmodel.sql.sqltypes.AutoString(length=250), nullable=True),
    sa.Column('contact_name', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
    sa.Column('contact_email', sqlmodel.sql.sqltypes.AutoString(length=320), nullable=True),
    sa.Column('contact_phone', sqlmodel.sql.sqltypes.AutoString(length=30), nullable=True),
    sa.Column('notes', sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=True),
    sa.Column('nit', sqlmodel.sql.sqltypes.AutoString(length=15), nullable=False),
    sa.Column('dv', sqlmodel.sql.sqltypes.AutoString(length=1), nullable=False),
    sa.Column('person_type', sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
    sa.Column('taxpayer_type', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
    sa.Column('legal_name', sqlmodel.sql.sqltypes.AutoString(length=250), nullable=True),
    sa.Column('first_name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
    sa.Column('middle_name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
    sa.Column('last_name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
    sa.Column('second_last_name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
    sa.Column('address', sqlmodel.sql.sqltypes.AutoString(length=250), nullable=True),
    sa.Column('department_code', sqlmodel.sql.sqltypes.AutoString(length=2), nullable=True),
    sa.Column('city_code', sqlmodel.sql.sqltypes.AutoString(length=5), nullable=True),
    sa.Column('rut_email', sqlmodel.sql.sqltypes.AutoString(length=320), nullable=True),
    sa.Column('rut_phone', sqlmodel.sql.sqltypes.AutoString(length=30), nullable=True),
    sa.Column('main_activity_code', sqlmodel.sql.sqltypes.AutoString(length=4), nullable=True),
    sa.Column('rut_status', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
    sa.Column('rut_generated_at', sa.Date(), nullable=True),
    sa.Column('rut_updated_at', sa.Date(), nullable=True),
    sa.Column('inactivation_reason', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    sa.CheckConstraint("(person_type = 'juridica' AND legal_name IS NOT NULL) OR (person_type = 'natural' AND first_name IS NOT NULL AND last_name IS NOT NULL)", name=op.f('ck_companies_name_matches_person_type')),
    sa.CheckConstraint("city_code ~ '^[0-9]{5}$'", name=op.f('ck_companies_city_code_dane')),
    sa.CheckConstraint("department_code ~ '^[0-9]{2}$'", name=op.f('ck_companies_department_code_dane')),
    sa.CheckConstraint("dv ~ '^[0-9]$'", name=op.f('ck_companies_dv_digit')),
    sa.CheckConstraint("main_activity_code ~ '^[0-9]{4}$'", name=op.f('ck_companies_main_activity_code_ciiu')),
    sa.CheckConstraint("nit ~ '^[0-9]{5,15}$'", name=op.f('ck_companies_nit_digits')),
    sa.CheckConstraint("person_type IN ('natural', 'juridica')", name=op.f('ck_companies_person_type_valid')),
    sa.ForeignKeyConstraint(['group_id'], ['exogena.groups.id'], name=op.f('fk_companies_group_id_groups')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_companies')),
    schema='exogena'
    )
    op.create_index(op.f('ix_exogena_companies_group_id'), 'companies', ['group_id'], unique=False, schema='exogena')
    op.create_index(op.f('ix_exogena_companies_organization_id'), 'companies', ['organization_id'], unique=False, schema='exogena')
    op.create_index('ux_companies_organization_nit', 'companies', ['organization_id', 'nit'], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.create_table('services',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('obligation_id', sa.Uuid(), nullable=False),
    sa.Column('service_type_id', sa.Uuid(), nullable=False),
    sa.Column('inactivation_reason', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    sa.ForeignKeyConstraint(['obligation_id'], ['exogena.obligations.id'], name=op.f('fk_services_obligation_id_obligations')),
    sa.ForeignKeyConstraint(['service_type_id'], ['exogena.service_types.id'], name=op.f('fk_services_service_type_id_service_types')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_services')),
    schema='exogena'
    )
    op.create_index(op.f('ix_exogena_services_obligation_id'), 'services', ['obligation_id'], unique=False, schema='exogena')
    op.create_index(op.f('ix_exogena_services_service_type_id'), 'services', ['service_type_id'], unique=False, schema='exogena')
    op.create_index(op.f('ix_exogena_services_tenant_id'), 'services', ['tenant_id'], unique=False, schema='exogena')
    op.create_index('ux_services_tenant_obligation_type', 'services', ['tenant_id', 'obligation_id', 'service_type_id'], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.create_table('company_rut_versions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('company_id', sa.Uuid(), nullable=False),
    sa.Column('generated_at', sa.Date(), nullable=True),
    sa.Column('rut_updated_at', sa.Date(), nullable=True),
    sa.Column('covers_tax_year', sa.Integer(), nullable=True),
    sa.Column('is_historical', sa.Boolean(), nullable=False),
    sa.Column('extraction_id', sa.Uuid(), nullable=True),
    sa.Column('file_key', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    sa.CheckConstraint('covers_tax_year BETWEEN 1990 AND 2100', name=op.f('ck_company_rut_versions_covers_tax_year_range')),
    sa.ForeignKeyConstraint(['company_id'], ['exogena.companies.id'], name=op.f('fk_company_rut_versions_company_id_companies')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_company_rut_versions')),
    schema='exogena'
    )
    op.create_index(op.f('ix_exogena_company_rut_versions_company_id'), 'company_rut_versions', ['company_id'], unique=False, schema='exogena')
    op.create_table('company_tax_responsibilities',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('company_id', sa.Uuid(), nullable=False),
    sa.Column('code', sqlmodel.sql.sqltypes.AutoString(length=2), nullable=False),
    sa.CheckConstraint("code ~ '^[0-9]{1,2}$'", name=op.f('ck_company_tax_responsibilities_code_digits')),
    sa.ForeignKeyConstraint(['company_id'], ['exogena.companies.id'], name=op.f('fk_company_tax_responsibilities_company_id_companies')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_company_tax_responsibilities')),
    schema='exogena'
    )
    op.create_index(op.f('ix_exogena_company_tax_responsibilities_company_id'), 'company_tax_responsibilities', ['company_id'], unique=False, schema='exogena')
    op.create_index('ux_company_tax_responsibilities_company_code', 'company_tax_responsibilities', ['company_id', 'code'], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.create_table('company_users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('company_id', sa.Uuid(), nullable=False),
    sa.Column('email', sqlmodel.sql.sqltypes.AutoString(length=320), nullable=False),
    sa.Column('full_name', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
    sa.Column('phone', sqlmodel.sql.sqltypes.AutoString(length=30), nullable=True),
    sa.Column('position', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.CheckConstraint('email = lower(email)', name=op.f('ck_company_users_email_lowercase')),
    sa.ForeignKeyConstraint(['company_id'], ['exogena.companies.id'], name=op.f('fk_company_users_company_id_companies')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_company_users')),
    schema='exogena'
    )
    op.create_index(op.f('ix_exogena_company_users_company_id'), 'company_users', ['company_id'], unique=False, schema='exogena')
    op.create_index(op.f('ix_exogena_company_users_user_id'), 'company_users', ['user_id'], unique=False, schema='exogena')
    op.create_index('ux_company_users_company_email', 'company_users', ['company_id', 'email'], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))
    op.create_table('engagements',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('company_id', sa.Uuid(), nullable=False),
    sa.Column('service_id', sa.Uuid(), nullable=False),
    sa.Column('obligation_id', sa.Uuid(), nullable=False),
    sa.Column('service_type_id', sa.Uuid(), nullable=False),
    sa.Column('fiscal_year', sa.Integer(), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
    sa.Column('partner_user_id', sa.Uuid(), nullable=False),
    sa.Column('manager_user_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("status IN ('por_iniciar', 'en_curso', 'cerrado')", name=op.f('ck_engagements_status_valid')),
    sa.CheckConstraint('fiscal_year BETWEEN 2000 AND 2100', name=op.f('ck_engagements_fiscal_year_range')),
    sa.ForeignKeyConstraint(['company_id'], ['exogena.companies.id'], name=op.f('fk_engagements_company_id_companies')),
    sa.ForeignKeyConstraint(['obligation_id'], ['exogena.obligations.id'], name=op.f('fk_engagements_obligation_id_obligations')),
    sa.ForeignKeyConstraint(['service_id'], ['exogena.services.id'], name=op.f('fk_engagements_service_id_services')),
    sa.ForeignKeyConstraint(['service_type_id'], ['exogena.service_types.id'], name=op.f('fk_engagements_service_type_id_service_types')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_engagements')),
    schema='exogena'
    )
    op.create_index(op.f('ix_exogena_engagements_company_id'), 'engagements', ['company_id'], unique=False, schema='exogena')
    op.create_index(op.f('ix_exogena_engagements_service_id'), 'engagements', ['service_id'], unique=False, schema='exogena')
    op.create_index(op.f('ix_exogena_engagements_tenant_id'), 'engagements', ['tenant_id'], unique=False, schema='exogena')
    op.create_index('ux_engagements_company_service_year', 'engagements', ['company_id', 'service_id', 'fiscal_year'], unique=True, schema='exogena', postgresql_where=sa.text('NOT is_deleted'))

    # Permisos: la app corre con su rol (wiseerp_app hoy; el rol propio del servicio cuando
    # se cree) y wiseerp_ro solo lee. Las tablas de futuras migraciones reciben los mismos
    # permisos (DEFAULT PRIVILEGES).
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
    for table in TABLES:
        op.drop_table(table, schema=SCHEMA)
    # El schema no se borra: en AWS lo crea un administrador y habría que pedirlo de nuevo
