from typing import Annotated

from fastapi import Depends

from app.core.database import SessionDep
from app.modules.clients.service import ClientService


def get_client_service(session: SessionDep) -> ClientService:
    return ClientService(session)


ClientServiceDep = Annotated[ClientService, Depends(get_client_service)]
