from app.modules.notes.dependencies import get_note_service
from app.modules.notes.schemas import NoteCreate, NoteRead, NoteUpdate
from app.shared.router import build_crud_router

# GET "", GET /{id}, POST "", PATCH /{id}, DELETE /{id} — todos requieren autenticación.
# Se pueden agregar endpoints propios con @router.get(...) debajo.
router = build_crud_router(
    service_dep=get_note_service,
    read_schema=NoteRead,
    create_schema=NoteCreate,
    update_schema=NoteUpdate,
)
