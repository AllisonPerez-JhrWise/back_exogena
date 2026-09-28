# Anotaciones diferidas: el método `list` taparía al builtin en las firmas siguientes
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar, Generic, TypeVar
from uuid import UUID

from sqlalchemy import ColumnElement, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlmodel.sql.expression import SelectOfScalar

from app.core.exceptions import BadRequestError
from app.shared.models import BaseTable
from app.shared.pagination import PageParams

ModelT = TypeVar("ModelT", bound=BaseTable)


class BaseRepository(Generic[ModelT]):
    """Solo acceso a datos: consultas, agregar, actualizar. Nunca hace commit;
    el service decide cuándo termina la transacción."""

    model: ClassVar[type[BaseTable]]
    # Columnas por las que el cliente puede ordenar (?sort=-created_at)
    sortable_fields: ClassVar[frozenset[str]] = frozenset({"created_at", "updated_at"})
    default_sort: ClassVar[str] = "-created_at"

    def __init__(self, session: AsyncSession):
        self.session = session

    def base_query(self) -> SelectOfScalar[ModelT]:
        return select(self.model).where(self.model.is_deleted.is_(False))

    async def get(self, item_id: UUID, *conditions: ColumnElement[bool]) -> ModelT | None:
        query = self.base_query().where(self.model.id == item_id, *conditions)
        result = await self.session.execute(query)
        return result.scalars().first()

    async def list(
        self, *conditions: ColumnElement[bool], params: PageParams
    ) -> tuple[Sequence[ModelT], int]:
        query = self.base_query().where(*conditions)

        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        query = query.order_by(*self._order_by(params.sort or self.default_sort))
        result = await self.session.execute(query.offset(params.offset).limit(params.size))
        return result.scalars().all(), total or 0

    async def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, obj: ModelT, values: dict[str, Any]) -> ModelT:
        for field, value in values.items():
            setattr(obj, field, value)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def soft_delete(self, obj: ModelT) -> None:
        obj.is_deleted = True
        self.session.add(obj)
        await self.session.flush()

    def _order_by(self, sort: str) -> list[Any]:
        field = sort.lstrip("-")
        if field not in self.sortable_fields:
            raise BadRequestError(
                f"Cannot sort by '{field}'",
                details={"allowed": sorted(self.sortable_fields)},
            )
        column = getattr(self.model, field)
        # id como desempate mantiene estable la paginación
        return [column.desc() if sort.startswith("-") else column.asc(), self.model.id]
