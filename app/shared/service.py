# Anotaciones diferidas: el método `list` taparía al builtin en las firmas siguientes
from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import ColumnElement
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.exceptions import NotFoundError
from app.shared.pagination import Page, PageParams
from app.shared.repository import BaseRepository, ModelT

CreateT = TypeVar("CreateT", bound=BaseModel)
UpdateT = TypeVar("UpdateT", bound=BaseModel)


class BaseService(Generic[ModelT, CreateT, UpdateT]):
    """Lógica de negocio y límite de la transacción (commit) de una entidad.

    Cuando sea posible, sobrescribir los hooks en lugar de los métodos CRUD:
      - scope(actor): filtros extra para toda lectura/edición/borrado
        (p. ej. "solo mis registros", "solo mi empresa").
      - prepare_create(values, actor): completar/validar valores antes de insertar.
      - prepare_update(obj, values, actor): lo mismo antes de actualizar.
    """

    repository_class: ClassVar[type[BaseRepository]]
    not_found_message: ClassVar[str] = "Resource not found"

    def __init__(self, session: Session):
        self.session = session
        self.repository: BaseRepository[ModelT] = self.repository_class(session)

    # ── Hooks ────────────────────────────────────────────────────────────
    def scope(self, actor: Principal | None) -> list[ColumnElement[bool]]:
        return []

    def prepare_create(self, values: dict[str, Any], actor: Principal | None) -> dict[str, Any]:
        return values

    def prepare_update(
        self, obj: ModelT, values: dict[str, Any], actor: Principal | None
    ) -> dict[str, Any]:
        return values

    # ── CRUD (crear, leer, actualizar, borrar) ──────────────────────────────
    def get(self, item_id: UUID, actor: Principal | None = None) -> ModelT:
        obj = self.repository.get(item_id, *self.scope(actor))
        if obj is None:
            raise NotFoundError(self.not_found_message)
        return obj

    def list(self, params: PageParams, actor: Principal | None = None) -> Page[ModelT]:
        items, total = self.repository.list(*self.scope(actor), params=params)
        return Page.create(items, total, params)

    def create(self, data: CreateT, actor: Principal | None = None) -> ModelT:
        values = data.model_dump()
        if actor:
            values["created_by"] = actor.id
        values = self.prepare_create(values, actor)

        obj = self.repository.add(self.repository.model.model_validate(values))
        self.session.commit()
        return obj

    def update(self, item_id: UUID, data: UpdateT, actor: Principal | None = None) -> ModelT:
        obj = self.get(item_id, actor)
        values = data.model_dump(exclude_unset=True)
        if actor:
            values["updated_by"] = actor.id
        values = self.prepare_update(obj, values, actor)

        obj = self.repository.update(obj, values)
        self.session.commit()
        return obj

    def delete(self, item_id: UUID, actor: Principal | None = None) -> None:
        obj = self.get(item_id, actor)
        if actor:
            obj.updated_by = actor.id
        self.repository.soft_delete(obj)
        self.session.commit()
