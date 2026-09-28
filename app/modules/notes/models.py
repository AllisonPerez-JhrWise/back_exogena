from uuid import UUID

from sqlmodel import Field

from app.shared.models import BaseTable


class Note(BaseTable):
    __tablename__ = "notes"

    title: str = Field(index=True, max_length=200)
    content: str
    # Dueño. UUID simple (sin FK): el usuario puede vivir en otro servicio
    user_id: UUID = Field(index=True)
