from app.modules.accounts.models import User
from app.modules.notes.models import Note
from app.shared.models import SQLModel, load_all_models

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


def test_every_table_has_base_columns():
    load_all_models()
    for table in SQLModel.metadata.tables.values():
        assert set(table.columns.keys()) >= BASE_COLUMNS, table.fullname


def test_audit_columns_have_no_foreign_keys():
    load_all_models()
    for table in SQLModel.metadata.tables.values():
        for column in ("created_by", "updated_by"):
            assert not table.columns[column].foreign_keys
