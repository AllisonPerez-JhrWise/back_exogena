"""compromisos según el acuerdo de datos (tarea A1)

Revision ID: 0002_engagements_data_agreement
Revises: 0001_initial
Create Date: 2026-10-01

El compromiso deja de crearse con un servicio del catálogo: lleva un tipo de servicio
(hoy solo "exogena"), fecha de inicio y los estados del acuerdo, con código en inglés.

- tenant_id pasa a llamarse organization_id.
- Nuevas: service_type (solo 'exogena') y start_date.
- due_date guarda fecha y hora (regla 4 del acuerdo).
- status: por_iniciar → created, en_curso → loading_documents, cerrado → closed.
- service_id, obligation_id, service_type_id, partner_user_id y manager_user_id quedan
  opcionales (no se borran).
- La regla "no repetir" pasa a ser empresa + tipo de servicio + año gravable.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_engagements_data_agreement"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "exogena"
TABLE = "engagements"

NEW_STATUSES = (
    "'created', 'loading_documents', 'ready_to_validate', 'validating', 'in_review', 'closed'"
)
OPTIONAL_COLUMNS = (
    "service_id",
    "obligation_id",
    "service_type_id",
    "partner_user_id",
    "manager_user_id",
)


def upgrade() -> None:
    # La organización (la firma) se llama igual que en el resto de servicios
    op.alter_column(TABLE, "tenant_id", new_column_name="organization_id", schema=SCHEMA)
    op.execute(
        f"ALTER INDEX {SCHEMA}.ix_exogena_engagements_tenant_id "
        "RENAME TO ix_exogena_engagements_organization_id"
    )

    # Tipo de servicio: las filas que ya existan quedan como exógena
    op.add_column(
        TABLE,
        sa.Column("service_type", sa.String(30), nullable=False, server_default="exogena"),
        schema=SCHEMA,
    )
    op.alter_column(TABLE, "service_type", server_default=None, schema=SCHEMA)
    op.create_check_constraint(
        op.f("ck_engagements_service_type_valid"),
        TABLE,
        "service_type IN ('exogena')",
        schema=SCHEMA,
    )

    # Fechas con hora
    op.add_column(
        TABLE, sa.Column("start_date", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA
    )
    op.alter_column(
        TABLE,
        "due_date",
        type_=sa.DateTime(timezone=True),
        postgresql_using="due_date::timestamptz",
        schema=SCHEMA,
    )

    # Estados del acuerdo, con código en inglés
    op.drop_constraint(op.f("ck_engagements_status_valid"), TABLE, schema=SCHEMA)
    op.execute(
        f"UPDATE {SCHEMA}.{TABLE} SET status = CASE status "
        "WHEN 'por_iniciar' THEN 'created' "
        "WHEN 'en_curso' THEN 'loading_documents' "
        "WHEN 'cerrado' THEN 'closed' END"
    )
    op.create_check_constraint(
        op.f("ck_engagements_status_valid"), TABLE, f"status IN ({NEW_STATUSES})", schema=SCHEMA
    )

    for column in OPTIONAL_COLUMNS:
        op.alter_column(TABLE, column, nullable=True, schema=SCHEMA)

    # REGLA DE NEGOCIO: no repetir tipo de servicio + año gravable en la misma empresa
    op.drop_index("ux_engagements_company_service_year", TABLE, schema=SCHEMA)
    op.create_index(
        "ux_engagements_company_service_type_year",
        TABLE,
        ["company_id", "service_type", "fiscal_year"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("NOT is_deleted"),
    )


def downgrade() -> None:
    """Solo funciona si todas las filas tienen servicio, socio y gerente (las creadas
    antes de esta migración). Los estados nuevos sin equivalente vuelven a en_curso."""
    op.drop_index("ux_engagements_company_service_type_year", TABLE, schema=SCHEMA)
    op.create_index(
        "ux_engagements_company_service_year",
        TABLE,
        ["company_id", "service_id", "fiscal_year"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("NOT is_deleted"),
    )

    for column in OPTIONAL_COLUMNS:
        op.alter_column(TABLE, column, nullable=False, schema=SCHEMA)

    op.drop_constraint(op.f("ck_engagements_status_valid"), TABLE, schema=SCHEMA)
    op.execute(
        f"UPDATE {SCHEMA}.{TABLE} SET status = CASE status "
        "WHEN 'created' THEN 'por_iniciar' "
        "WHEN 'closed' THEN 'cerrado' "
        "ELSE 'en_curso' END"
    )
    op.create_check_constraint(
        op.f("ck_engagements_status_valid"),
        TABLE,
        "status IN ('por_iniciar', 'en_curso', 'cerrado')",
        schema=SCHEMA,
    )

    op.alter_column(
        TABLE,
        "due_date",
        type_=sa.Date(),
        postgresql_using="due_date::date",
        schema=SCHEMA,
    )
    op.drop_column(TABLE, "start_date", schema=SCHEMA)

    op.drop_constraint(op.f("ck_engagements_service_type_valid"), TABLE, schema=SCHEMA)
    op.drop_column(TABLE, "service_type", schema=SCHEMA)

    op.execute(
        f"ALTER INDEX {SCHEMA}.ix_exogena_engagements_organization_id "
        "RENAME TO ix_exogena_engagements_tenant_id"
    )
    op.alter_column(TABLE, "organization_id", new_column_name="tenant_id", schema=SCHEMA)
