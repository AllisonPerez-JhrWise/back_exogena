from fastapi import APIRouter, status

from app.modules.clients.dependencies import ClientServiceDep
from app.modules.clients.schemas import ClientCreate, ClientRead
from app.modules.platform.dependencies import CanCreateClientsDep
from app.shared.responses import ApiResponse

router = APIRouter()


@router.post(
    "",
    response_model=ApiResponse[ClientRead],
    status_code=status.HTTP_201_CREATED,
    summary="Crear cliente (formulario 'Nuevo cliente')",
)
async def create_client(data: ClientCreate, service: ClientServiceDep, actor: CanCreateClientsDep):
    """Requiere el permiso `clientes.crear` en el tenant del encabezado X-Tenant-Id.
    Crea el cliente en la plataforma, sus datos del RUT y sus usuarios en una sola
    transacción."""
    return ApiResponse(message="Client created", data=await service.create(data, actor))
