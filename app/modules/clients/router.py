from fastapi import APIRouter, status

from app.modules.accounts.dependencies import AdminDep
from app.modules.clients.dependencies import ClientServiceDep
from app.modules.clients.schemas import ClientCreate, ClientRead
from app.shared.responses import ApiResponse

router = APIRouter()


@router.post(
    "",
    response_model=ApiResponse[ClientRead],
    status_code=status.HTTP_201_CREATED,
    summary="Crear cliente (formulario 'Nuevo cliente')",
)
async def create_client(data: ClientCreate, service: ClientServiceDep, admin: AdminDep):
    """Solo administradores. Crea el cliente, sus responsabilidades y sus usuarios
    en una sola transacción."""
    return ApiResponse(message="Client created", data=await service.create(data, admin))
