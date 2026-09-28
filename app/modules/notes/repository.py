from app.modules.notes.models import Note
from app.shared.repository import BaseRepository


class NoteRepository(BaseRepository[Note]):
    model = Note
    sortable_fields = frozenset({"created_at", "updated_at", "title"})
