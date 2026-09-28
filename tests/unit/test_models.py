from sqlalchemy import Index

from app.modules.accounts.models import Role, User, UserIdentity, UserRole
from app.modules.clients.models import (
    Client,
    ClientTaxResponsibility,
    ClientUser,
    PersonType,
)
from app.modules.notes.models import Note
from app.shared.models import SQLModel, _with_schema, join_name_parts, load_all_models

BASE_COLUMNS = {
    "id",
    "is_deleted",
    "is_active",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
}


def test_schema_comes_from_module_name():
    assert User.__table__.schema == "accounts"
    assert Note.__table__.schema == "notes"
    # También con __table_args__ en forma de tupla (índices y checks)
    for model in (Role, UserRole, UserIdentity):
        assert model.__table__.schema == "accounts"
    for model in (Client, ClientTaxResponsibility, ClientUser):
        assert model.__table__.schema == "clients"


def test_with_schema_keeps_explicit_schema_and_other_args():
    index = Index("ix_demo", "x")
    assert _with_schema(None, "m") == {"schema": "m"}
    assert _with_schema({"comment": "c"}, "m") == {"schema": "m", "comment": "c"}
    assert _with_schema({"schema": "otro"}, "m") == {"schema": "otro"}
    assert _with_schema((index,), "m") == (index, {"schema": "m"})
    assert _with_schema((index, {"schema": "otro"}), "m") == (index, {"schema": "otro"})


def test_every_table_has_base_columns():
    load_all_models()
    for table in SQLModel.metadata.tables.values():
        assert set(table.columns.keys()) >= BASE_COLUMNS, table.fullname


def test_audit_columns_have_no_foreign_keys():
    load_all_models()
    for table in SQLModel.metadata.tables.values():
        for column in ("created_by", "updated_by"):
            assert not table.columns[column].foreign_keys


def test_join_name_parts_skips_empty_parts():
    assert join_name_parts("Paula", None, "Córdoba", "") == "Paula Córdoba"
    assert join_name_parts(" Carlos ", "Andrés", "Mejía", None) == "Carlos Andrés Mejía"


def test_full_name_is_built_from_parts():
    user = User(email="p@x.co", first_name="Paula", last_name="Córdoba", second_last_name="Ruiz")
    assert user.full_name == "Paula Córdoba Ruiz"


def test_client_display_name_depends_on_person_type():
    empresa = Client(
        nit="900123456", dv="4", person_type=PersonType.JURIDICA, legal_name="Andina SAS"
    )
    persona = Client(
        nit="1020304050",
        dv="1",
        person_type=PersonType.NATURAL,
        first_name="Juan",
        middle_name="Pablo",
        last_name="Restrepo",
    )
    assert empresa.display_name == "Andina SAS"
    assert persona.display_name == "Juan Pablo Restrepo"
