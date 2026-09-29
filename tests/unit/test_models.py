from sqlalchemy import Index

from app.modules.clients.models import (
    Company,
    CompanyRutVersion,
    CompanyTaxResponsibility,
    CompanyUser,
    Group,
    PersonType,
)
from app.modules.clients.schemas import CompanyUserIn
from app.modules.platform.models import Membership, Tenant, User
from app.shared.models import (
    DB_SCHEMA,
    SQLModel,
    _with_schema,
    join_name_parts,
    load_all_models,
)

BASE_COLUMNS = {
    "id",
    "is_deleted",
    "is_active",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
}


def own_tables():
    """Tablas de este servicio (las de la plataforma tienen otra forma y no son nuestras)."""
    load_all_models()
    return [t for t in SQLModel.metadata.tables.values() if t.schema == DB_SCHEMA]


def test_own_tables_live_in_service_schema():
    # También con __table_args__ en forma de tupla (índices y checks)
    for model in (Company, CompanyTaxResponsibility, CompanyRutVersion, CompanyUser, Group):
        assert model.__table__.schema == DB_SCHEMA
    for model in (User, Tenant, Membership):
        assert model.__table__.schema is None  # schema por defecto (public)


def test_with_schema_keeps_explicit_schema_and_other_args():
    index = Index("ix_demo", "x")
    assert _with_schema(None, "m") == {"schema": "m"}
    assert _with_schema({"comment": "c"}, "m") == {"schema": "m", "comment": "c"}
    assert _with_schema({"schema": "otro"}, "m") == {"schema": "otro"}
    assert _with_schema((index,), "m") == (index, {"schema": "m"})
    assert _with_schema((index, {"schema": "otro"}), "m") == (index, {"schema": "otro"})


def test_every_own_table_has_base_columns():
    for table in own_tables():
        assert set(table.columns.keys()) >= BASE_COLUMNS, table.fullname


def test_audit_columns_have_no_foreign_keys():
    for table in own_tables():
        for column in ("created_by", "updated_by"):
            assert not table.columns[column].foreign_keys


def test_join_name_parts_skips_empty_parts():
    assert join_name_parts("Paula", None, "Córdoba", "") == "Paula Córdoba"
    assert join_name_parts(" Carlos ", "Andrés", "Mejía", None) == "Carlos Andrés Mejía"


def test_platform_full_name_is_built_from_parts():
    user = CompanyUserIn(
        email="p@x.co", first_name="Paula", last_name="Córdoba", second_last_name="Ruiz"
    )
    assert user.full_name == "Paula Córdoba Ruiz"


def test_client_display_name_depends_on_person_type():
    empresa = Company(
        nit="900123456", dv="4", person_type=PersonType.JURIDICA, legal_name="Andina SAS"
    )
    persona = Company(
        nit="1020304050",
        dv="1",
        person_type=PersonType.NATURAL,
        first_name="Juan",
        middle_name="Pablo",
        last_name="Restrepo",
    )
    assert empresa.display_name == "Andina SAS"
    assert persona.display_name == "Juan Pablo Restrepo"
