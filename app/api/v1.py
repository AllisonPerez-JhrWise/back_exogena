from fastapi import APIRouter

from app.modules.catalog.router import obligations_router, service_types_router
from app.modules.clients.router import companies_router, groups_router
from app.modules.clients.router import router as clients_router
from app.modules.engagements.router import engagements_router
from app.modules.engagements.router import router as company_engagements_router

# Aquí se registra el router de cada módulo
router = APIRouter()
router.include_router(clients_router, prefix="/clients", tags=["Clients"])
router.include_router(companies_router, prefix="/companies", tags=["Companies"])
router.include_router(groups_router, prefix="/groups", tags=["Groups"])
router.include_router(company_engagements_router, prefix="/companies", tags=["Engagements"])
router.include_router(engagements_router, prefix="/engagements", tags=["Engagements"])
router.include_router(obligations_router, prefix="/obligations", tags=["Catalog"])
router.include_router(service_types_router, prefix="/service-types", tags=["Catalog"])
