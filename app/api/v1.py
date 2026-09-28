from fastapi import APIRouter

from app.modules.accounts.router import auth_router, users_router
from app.modules.clients.router import router as clients_router
from app.modules.notes.router import router as notes_router

# Aquí se registra el router de cada módulo
router = APIRouter()
router.include_router(auth_router, prefix="/auth", tags=["Auth"])
router.include_router(users_router, prefix="/users", tags=["Users"])
router.include_router(clients_router, prefix="/clients", tags=["Clients"])
router.include_router(notes_router, prefix="/notes", tags=["Notes (example)"])
