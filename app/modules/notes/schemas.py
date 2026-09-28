from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NoteCreate(BaseModel):
    # user_id se toma del usuario autenticado, nunca del body
    title: str = Field(min_length=1, max_length=200)
    content: str


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = None


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    content: str
    user_id: UUID
    created_at: datetime
    updated_at: datetime | None = None
