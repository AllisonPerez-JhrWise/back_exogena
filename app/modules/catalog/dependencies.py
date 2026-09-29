from typing import Annotated

from fastapi import Depends

from app.core.database import SessionDep
from app.modules.catalog.service import CatalogService


def get_catalog_service(session: SessionDep) -> CatalogService:
    return CatalogService(session)


CatalogServiceDep = Annotated[CatalogService, Depends(get_catalog_service)]
