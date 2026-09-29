from typing import Annotated

from fastapi import Depends

from app.core.database import SessionDep
from app.modules.engagements.service import EngagementService


def get_engagement_service(session: SessionDep) -> EngagementService:
    return EngagementService(session)


EngagementServiceDep = Annotated[EngagementService, Depends(get_engagement_service)]
