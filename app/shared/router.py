from collections.abc import Callable, Iterable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.core.auth import Principal, get_current_principal
from app.shared.pagination import Page, PageParamsDep
from app.shared.responses import ApiResponse
from app.shared.service import BaseService

CRUD_ACTIONS = ("list", "get", "create", "update", "delete")


def build_crud_router(
    *,
    service_dep: Callable[..., BaseService],
    read_schema: type[BaseModel],
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    actions: Iterable[str] = CRUD_ACTIONS,
    auth_dep: Callable[..., Any] = get_current_principal,
) -> APIRouter:
    """Endpoints CRUD estándar y autenticados sobre un BaseService.

    Las reglas de negocio viven en el service (hooks scope / prepare_*), no aquí.
    Los endpoints propios se agregan al router devuelto de la forma normal.
    """
    router = APIRouter()
    actions = set(actions)
    ServiceDep = Annotated[BaseService, Depends(service_dep)]
    ActorDep = Annotated[Principal, Depends(auth_dep)]

    if "list" in actions:

        @router.get("", response_model=ApiResponse[Page[read_schema]])
        async def list_items(service: ServiceDep, actor: ActorDep, params: PageParamsDep):
            return ApiResponse(data=await service.list(params, actor))

    if "get" in actions:

        @router.get("/{item_id}", response_model=ApiResponse[read_schema])
        async def get_item(item_id: UUID, service: ServiceDep, actor: ActorDep):
            return ApiResponse(data=await service.get(item_id, actor))

    if "create" in actions:

        @router.post(
            "",
            response_model=ApiResponse[read_schema],
            status_code=status.HTTP_201_CREATED,
        )
        async def create_item(data: create_schema, service: ServiceDep, actor: ActorDep):  # type: ignore[valid-type]
            return ApiResponse(message="Created", data=await service.create(data, actor))

    if "update" in actions:

        @router.patch("/{item_id}", response_model=ApiResponse[read_schema])
        async def update_item(
            item_id: UUID,
            data: update_schema,  # type: ignore[valid-type]
            service: ServiceDep,
            actor: ActorDep,
        ):
            return ApiResponse(message="Updated", data=await service.update(item_id, data, actor))

    if "delete" in actions:

        @router.delete("/{item_id}", response_model=ApiResponse[None])
        async def delete_item(item_id: UUID, service: ServiceDep, actor: ActorDep):
            await service.delete(item_id, actor)
            return ApiResponse(message="Deleted")

    return router
