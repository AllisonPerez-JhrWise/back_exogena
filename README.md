# back_exogena

FastAPI microservice (async SQLModel + PostgreSQL on AWS RDS) consumed by a Next.js micro-frontend.

## Architecture

Code is organized **by business module**, and each module is split into layers:

```
app/
├── main.py                 # create_app(): middleware, handlers, routers
├── core/                   # Infrastructure shared by everything (no business logic)
│   ├── config.py           # Settings: the ONLY place that reads env vars
│   ├── database.py         # Async engine, session per request (SessionDep)
│   ├── auth.py             # JWT -> Principal (PrincipalDep). No DB access
│   ├── security.py         # Password hashing (Argon2), JWT encode/decode
│   ├── exceptions.py       # Domain errors: NotFoundError, ConflictError, ...
│   ├── handlers.py         # Domain errors / DB errors -> JSON error envelope
│   ├── middleware.py       # X-Request-ID + one log line per request
│   └── logging.py          # JSON logs (CloudWatch) outside local
├── shared/                 # Reusable building blocks for modules
│   ├── models.py           # BaseTable (id, audit, soft delete) + service schema (DB_SCHEMA)
│   ├── repository.py       # BaseRepository: queries, never commits
│   ├── service.py          # BaseService: business rules + commit (hooks)
│   ├── router.py           # build_crud_router(): standard CRUD endpoints
│   ├── pagination.py       # PageParams (?page&size&sort) and Page[T]
│   └── responses.py        # ApiResponse[T] / ErrorResponse envelopes
├── api/
│   ├── health.py           # /health (liveness), /health/ready (DB check)
│   └── v1.py               # Registers every module router under /api/v1
└── modules/
    ├── platform/           # Read-only models of the platform tables (public) + permissions
    ├── clients/            # Client registration: companies (one per NIT), groups, RUT versions
    ├── engagements/        # Engagements of a company (service + fiscal year, partner, manager)
    └── catalog/            # Obligations, service types and services (reference module)
        └── (every module)  # same layers:
        ├── models.py       # Tables (all in the "exogena" schema)
        ├── schemas.py      # Request/response Pydantic models
        ├── repository.py   # Data access
        ├── service.py      # Business rules
        ├── dependencies.py # get_<x>_service for FastAPI DI
        └── router.py       # HTTP endpoints
```

### Layer rules

| Layer | Does | Never |
|---|---|---|
| `router.py` | HTTP: parse input, call the service, wrap in `ApiResponse` | Queries, business rules |
| `service.py` | Business rules, permissions (`scope`), **commit** | Import FastAPI, raise `HTTPException` |
| `repository.py` | SQL queries, `add`/`update`/`soft_delete` with `flush` | `commit`, business rules |
| `models.py` | Tables | Relationships to other modules' tables |

- Services raise domain errors from `app.core.exceptions`; `core/handlers.py` turns them into HTTP responses.
- Dependencies are injected per request (`Depends(get_note_service)`), so tests can swap any service for a fake.
- Modules do not import each other's internals. Tables of this service use real FKs between them and to the platform tables (same database).
- Every table gets `id`, `is_deleted`, `is_active`, `created_at`, `updated_at`, `created_by`, `updated_by`, and lives in the single PostgreSQL schema `exogena` (`DB_SCHEMA` in `app/shared/models.py`). Modules split the code, not the database.

### API contract (for the Next.js front)

```jsonc
// success
{ "ok": true,  "message": "OK", "data": { ... } }
// list
{ "ok": true,  "message": "OK", "data": { "items": [], "total": 0, "page": 1, "size": 20, "pages": 0 } }
// error
{ "ok": false, "message": "Note not found", "code": "not_found", "details": null }
```

- Lists: `?page=1&size=20&sort=-created_at` (max size 100, sortable fields are whitelisted per repository).
- Error `code` values: `bad_request`, `unauthorized`, `forbidden`, `not_found`, `conflict`, `business_rule`, `validation_error`, `integrity_error`, `internal_error`.
- Every response carries `X-Request-ID` (send your own from the BFF to correlate logs).
- The OpenAPI schema (`/openapi.json`, disabled in production) is typed, so TS types can be generated with `openapi-typescript`.

### Authentication

- Login is **not** part of this service: the platform handles it with AWS Cognito. Like every service, it uses `wise-comun`: it validates the Cognito **access token** (`Authorization: Bearer <token>`), reads the active organization from `X-Organization-Id` and asks Identidad (`GET /autorizacion`, at `IDENTIDAD_URL`) who the person is, their roles and assignments. This service never reads Identidad's tables.
- Endpoints require **permissions, never roles**: `exige(permiso)` (see `app/core/auth.py`). Reading is having the permission at level *Consulta* (`exige(..., lectura=True)`). The `Decision` it returns says the scope (whole organization, their engagements or their companies), which filters the clients screen.
- The DB session is `wise_comun.db`: it sets the row-level security context (`app.user_id`, `app.organization_id`) per transaction.
- **Local development without a platform user:** `AUTH_BYPASS=true` (never in production) acts as Administrator of `DEV_ORGANIZATION_ID` without a token (`app/core/dev_access.py`). Tests use an in-memory double of Identidad (`tests/integration/identity.py`).

### Identidad data

- People, organizations, roles, memberships and assignments belong to Identidad (wise-auth, schema `identidad`). People and memberships are created there (`POST /organizacion/miembros`). Our tables store their IDs (organization, users) **without foreign keys**, like every service of the platform.
- The app connects with `DB_USER`; migrations run as the owner of `exogena` (`DB_ADMIN_USER`).

## Adding a new module

1. Create `app/modules/<name>/` with the same files as `app/modules/catalog/`.
2. Define the table in `models.py` (inherit `BaseTable`, set `__tablename__`).
3. Put permission/ownership rules in the service hooks: `scope`, `prepare_create`, `prepare_update`.
4. Register the router in `app/api/v1.py`.
5. `make migration m="add_<name>"`, review the generated file, `make migrate`.
6. Add unit tests (fake service) and integration tests (real DB) under `tests/`.

## Getting started

> 📘 **Guía completa en español:** [docs/GUIA_LOCAL.md](docs/GUIA_LOCAL.md) (qué es Docker, cómo instalar `make` en Windows, todos los comandos y solución de problemas).

Requirements: Docker Desktop, Git and `make` (on Windows: `winget install ezwinports.make`; works from PowerShell or Git Bash). Python is only needed for the optional local `.venv`.

```bash
make up      # creates .env (with a random JWT_SECRET) if missing, starts app + local
             # PostgreSQL in the background, waits until healthy and applies migrations
```

Then open http://localhost:8000/docs. Run `make` to list every command.

| Command | Description |
|---|---|
| `make up` / `make down` | Start everything (ready to use) / stop (data is kept) |
| `make status` / `make logs` / `make restart` | Container status / follow app logs / restart the app |
| `make shell` / `make psql` | Shell inside the app container / SQL console of the local DB |
| `make reset` | Wipe the local database and start from scratch (asks for confirmation) |
| `make migrate` / `make migration m="..."` / `make db-check` | Apply / autogenerate / verify migrations |
| `make test` | Unit + integration tests in Docker (throwaway DB) |
| `make venv` | Optional local `.venv` (editor, `test-unit`, `lint`, `format`) |

## Deploying to AWS

- Build the `Dockerfile` (non-root, multi-stage). Workers via `WEB_CONCURRENCY`.
- Inject `DATABASE_URL` and `JWT_SECRET` from **Secrets Manager**; never commit them.
- RDS: `DB_SSL_MODE=require`, not publicly accessible, security group open only to the service. Use a dedicated DB role for the app (DML only) and another for migrations (DDL). Consider RDS Proxy if many tasks share the instance.
- Connections per task = `WEB_CONCURRENCY × (DB_POOL_SIZE + DB_MAX_OVERFLOW)`; keep the total below the RDS `max_connections`.
- Run `alembic upgrade head` as a separate step (CI job or one-off ECS task) before rolling out, never at app startup. Alembic uses its own version table (`alembic_version_exogena`) and only touches this service's schema, because the database is shared.
- Health checks: ALB → `/health`, readiness → `/health/ready`.
- `ENVIRONMENT=production` enforces `COOKIE_SECURE=true`, forbids `*` in CORS and hides `/docs`.

## Branching

- `main`: production. `develop`: integration.
- Work in `feature/<name>` branches from `develop` and open PRs into `develop`.
