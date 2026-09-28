from sqlmodel import Field

from app.shared.models import BaseTable


class User(BaseTable):
    __tablename__ = "users"

    email: str = Field(unique=True, index=True, nullable=False)
    username: str | None = Field(default=None, unique=True, index=True)
    full_name: str | None = None
    hashed_password: str | None = None
    google_id: str | None = Field(default=None, index=True)
    avatar_url: str | None = None
