from app.core.database import SessionDep
from app.modules.notes.service import NoteService


def get_note_service(session: SessionDep) -> NoteService:
    return NoteService(session)
