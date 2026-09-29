from typing import Annotated

from fastapi import Depends

from app.core.database import SessionDep
from app.modules.clients.service import ClientService, GroupService


def get_client_service(session: SessionDep) -> ClientService:
    return ClientService(session)


def get_group_service(session: SessionDep) -> GroupService:
    return GroupService(session)


ClientServiceDep = Annotated[ClientService, Depends(get_client_service)]
GroupServiceDep = Annotated[GroupService, Depends(get_group_service)]
