from typing import Any

from sqlalchemy import ColumnElement

from app.core.auth import Principal
from app.modules.notes.models import Note
from app.modules.notes.repository import NoteRepository
from app.modules.notes.schemas import NoteCreate, NoteUpdate
from app.shared.service import BaseService


class NoteService(BaseService[Note, NoteCreate, NoteUpdate]):
    repository_class = NoteRepository
    not_found_message = "Note not found"

    def scope(self, actor: Principal | None) -> list[ColumnElement[bool]]:
        # Cada usuario solo ve y modifica sus propias notas.
        # Las notas de otros responden 404 (no 403) para no revelar que existen.
        return [Note.user_id == actor.id]

    async def prepare_create(
        self, values: dict[str, Any], actor: Principal | None
    ) -> dict[str, Any]:
        values["user_id"] = actor.id
        return values
