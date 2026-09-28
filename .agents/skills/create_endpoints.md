# Skill: Creating a New Module / Endpoints

The project is organized by business module under `app/modules/<module>/`, each
with layers: router → service → repository → model. `app/modules/notes/` is the
reference implementation; copy it.

## 1. Model (`models.py`)

```python
from uuid import UUID
from sqlmodel import Field
from app.shared.models import DB_SCHEMA, BaseTable


class Invoice(BaseTable):  # -> table exogena.invoices (every table lives in DB_SCHEMA)
    __tablename__ = "invoices"

    number: str = Field(index=True, max_length=30)
    total: int
    # Same schema, so tables of this service use a real FK; build it with DB_SCHEMA
    client_id: UUID = Field(foreign_key=f"{DB_SCHEMA}.clients.id", index=True)
```

`BaseTable` already adds `id`, `is_deleted`, `is_active`, `created_at`, `updated_at`,
`created_by`, `updated_by`. Never use `sa_column=Column(...)` in shared base classes.

## 2. Schemas (`schemas.py`)

Separate `XCreate`, `XUpdate` (all optional, for PATCH) and `XRead`
(`model_config = ConfigDict(from_attributes=True)`). Never expose secrets in `XRead`.
Fields the server decides (owner, company, status) are NOT in `XCreate`.

## 3. Repository (`repository.py`)

```python
from app.shared.repository import BaseRepository


class InvoiceRepository(BaseRepository[Invoice]):
    model = Invoice
    sortable_fields = frozenset({"created_at", "number", "total"})

    async def get_by_number(self, number: str) -> Invoice | None:
        result = await self.session.execute(self.base_query().where(Invoice.number == number))
        return result.scalars().first()
```

- Always start from `self.base_query()` (it excludes soft-deleted rows).
- Repositories `flush`, they never `commit`.

## 4. Service (`service.py`)

```python
from app.core.exceptions import ConflictError
from app.shared.service import BaseService


class InvoiceService(BaseService[Invoice, InvoiceCreate, InvoiceUpdate]):
    repository_class = InvoiceRepository
    not_found_message = "Invoice not found"

    def scope(self, actor):                       # filters for every read/update/delete
        return []

    async def prepare_create(self, values, actor):
        if await self.repository.get_by_number(values["number"]):
            raise ConflictError("Invoice number already exists")
        return values
```

- Business rules and permissions live here. Raise errors from `app.core.exceptions`
  (`NotFoundError`, `ConflictError`, `ForbiddenError`, `BusinessRuleError`...).
  **Never** import FastAPI or raise `HTTPException` in a service.
- The service owns the transaction: `await self.session.commit()` once per use case.
  Several repositories in one method = one transaction.

## 5. Dependencies (`dependencies.py`)

```python
from app.core.database import SessionDep


def get_invoice_service(session: SessionDep) -> InvoiceService:
    return InvoiceService(session)
```

## 6. Router (`router.py`)

Standard CRUD (authenticated list/get/create/PATCH/delete):

```python
from app.shared.router import build_crud_router

router = build_crud_router(
    service_dep=get_invoice_service,
    read_schema=InvoiceRead,
    create_schema=InvoiceCreate,
    update_schema=InvoiceUpdate,
    actions=("list", "get", "create"),   # optional subset
)
```

Custom endpoint on the same router:

```python
from typing import Annotated
from fastapi import Depends
from app.core.auth import PrincipalDep
from app.shared.responses import ApiResponse

InvoiceServiceDep = Annotated[InvoiceService, Depends(get_invoice_service)]


@router.post("/{item_id}/approve", response_model=ApiResponse[InvoiceRead])
async def approve(item_id: UUID, service: InvoiceServiceDep, actor: PrincipalDep):
    return ApiResponse(message="Approved", data=await service.approve(item_id, actor))
```

Always return `ApiResponse(...)` with a `response_model=ApiResponse[...]`.

## 7. Register and migrate

1. `app/api/v1.py`: `router.include_router(invoices_router, prefix="/invoices", tags=["Invoices"])`
2. `make migration m="add_invoices"`, review the file, `make migrate`.

## Checklist

- [ ] No queries in routers/services, no business rules in routers/repositories
- [ ] No `HTTPException` outside routers; no `commit` outside services
- [ ] Owner/company fields set by the service, not accepted from the body
- [ ] `sortable_fields` whitelisted
- [ ] Unit test with a fake service + integration test with the DB
