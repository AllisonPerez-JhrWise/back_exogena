# Skill: Writing Tests

```
tests/
├── conftest.py            # safe env defaults, one event loop, auto "integration" marker
├── unit/                  # no database: fake services via dependency overrides
│   └── conftest.py        # client, principal, authenticated fixtures
└── integration/           # real PostgreSQL, each test rolled back
    └── conftest.py        # engine, db_session, client, register fixtures
```

- `make test-unit`: unit tests only (no DB).
- `make test`: everything in Docker with a throwaway PostgreSQL.
- Tests are `async def` without decorators (`asyncio_mode = auto`).

## Unit: router with a fake service

Override the module's `get_<x>_service`; the fake implements only what the test uses.

```python
from app.main import app
from app.modules.invoices.dependencies import get_invoice_service


class FakeInvoiceService:
    async def get(self, item_id, actor):
        raise NotFoundError("Invoice not found")


@pytest.fixture
def service():
    fake = FakeInvoiceService()
    app.dependency_overrides[get_invoice_service] = lambda: fake
    return fake


async def test_not_found(client, service, authenticated):
    response = await client.get(f"/api/v1/invoices/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
```

`authenticated` logs in a fake `Principal`; without it protected routes return 401.

## Unit: service logic

Services receive the session in the constructor, so pure rules can be tested by
replacing the repository:

```python
service = InvoiceService(session=AsyncMock())
service.repository = FakeInvoiceRepository()
```

## Integration: full flow against PostgreSQL

The `client` fixture uses a session inside a transaction that is rolled back after
each test (service commits become savepoints), so tests do not affect each other.
The test database has the platform tables (docker/db-init) and every API request runs as
`wiseerp_app`, so row-level security applies as in AWS.

```python
async def test_invoice_flow(client, admin, staff):
    # admin: headers (Bearer token + X-Tenant-Id) of a firm administrator
    created = await client.post("/api/v1/invoices", json={...}, headers=admin)
    assert created.status_code == 201
    # staff(email, role): another person of the firm with that system role
    asociado = await staff("ana@jhrwise.com", SystemRole.ASOCIADO)
```

Prepare platform data with the `platform` fixture (`user`, `tenant`, `member`).

## Rules

- Assert on the envelope: `ok`, `data`, `code` for errors.
- Test permission scoping with two users (the other user must get 404).
- Never point tests at a real `.env` database: `tests/conftest.py` sets safe defaults.
