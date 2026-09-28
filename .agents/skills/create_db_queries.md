# Skill: Writing Database Queries

All SQL lives in the module's `repository.py` (`app/modules/<module>/repository.py`),
in a class inheriting `app.shared.repository.BaseRepository`. The repository receives
the `AsyncSession` in its constructor (`self.session`).

## Rules

- Start every query from `self.base_query()`: it already excludes soft-deleted rows.
- Repositories **never** call `commit()`. Use `flush()` when you need generated
  values; the service commits.
- Never build SQL with f-strings from user input. Use SQLAlchemy expressions.
- Sorting from the client only on `sortable_fields`.
- Return models or plain values, not HTTP responses; raise `app.core.exceptions`
  errors if needed (e.g. `BadRequestError`).

## Base methods available

| Method | Description |
|---|---|
| `get(id, *conditions)` | One row or `None` |
| `list(*conditions, params=PageParams)` | `(items, total)` paginated and sorted |
| `add(obj)` | Insert + flush + refresh |
| `update(obj, values: dict)` | Set attributes + flush + refresh |
| `soft_delete(obj)` | `is_deleted = True` + flush |

## Examples

```python
from sqlalchemy import func
from sqlmodel import select


class InvoiceRepository(BaseRepository[Invoice]):
    model = Invoice

    async def get_by_number(self, number: str) -> Invoice | None:
        result = await self.session.execute(self.base_query().where(Invoice.number == number))
        return result.scalars().first()

    async def list_by_customer(self, customer_id: UUID) -> Sequence[Invoice]:
        result = await self.session.execute(
            self.base_query().where(Invoice.customer_id == customer_id).order_by(Invoice.number)
        )
        return result.scalars().all()

    async def totals_by_status(self) -> list[tuple[str, int]]:
        query = (
            select(Invoice.status, func.sum(Invoice.total))
            .where(Invoice.is_deleted.is_(False))
            .group_by(Invoice.status)
        )
        return (await self.session.execute(query)).all()
```

Paginated list with a module-specific filter: pass conditions to the base `list`.

```python
items, total = await self.repository.list(Invoice.status == "open", params=params)
```

## Transactions (in the service)

```python
async def pay(self, invoice_id, actor):
    invoice = await self.get(invoice_id, actor)
    await self.repository.update(invoice, {"status": "paid", "updated_by": actor.id})
    await self.payments.add(Payment(invoice_id=invoice.id, amount=invoice.total))
    await self.session.commit()   # both writes or none
    return invoice
```
