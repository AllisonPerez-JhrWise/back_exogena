from uuid import UUID

from sqlmodel import Field

from app.modules.platform.models import platform_fk
from app.shared.models import BaseTable


class Note(BaseTable):
    __tablename__ = "notes"

    title: str = Field(index=True, max_length=200)
    content: str
    # Dueño: una persona de la plataforma
    user_id: UUID = Field(foreign_key=platform_fk("users"), index=True)
