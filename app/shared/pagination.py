import math
from collections.abc import Sequence
from typing import Annotated, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field

T = TypeVar("T")

MAX_PAGE_SIZE = 100


class PageParams(BaseModel):
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=MAX_PAGE_SIZE)
    # Nombre de la columna, con prefijo "-" para orden descendente: "-created_at"
    sort: str | None = Field(None, pattern=r"^-?[a-z_][a-z0-9_]*$")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


PageParamsDep = Annotated[PageParams, Query()]


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int

    @classmethod
    def create(cls, items: Sequence[T], total: int, params: PageParams) -> "Page[T]":
        return cls(
            items=list(items),
            total=total,
            page=params.page,
            size=params.size,
            pages=math.ceil(total / params.size) if total else 0,
        )
