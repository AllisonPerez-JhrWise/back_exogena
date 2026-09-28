"""Tablas de la plataforma (schema public), tal como existen en la RDS.

NO son de este servicio: las crea y las cambia el servicio de plataforma con su propio
Alembic (alembic/env.py las excluye de nuestras migraciones). Aquí solo se describen para
consultarlas y para que las tablas de exogena les apunten con FK. Si la plataforma cambia
una columna, se actualiza aquí a mano (ver `make db-sync-cloud`).

Todas tienen seguridad por filas (RLS): cada consulta solo ve lo que permiten
`app.user_id` y `app.tenant_id` (ver app.core.database.set_db_context).

Se declaran SIN schema: public es el schema por defecto (search_path), y así las FK
coinciden con lo que PostgreSQL reporta y autogenerate no las ve como distintas.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlmodel import DateTime, Field, SQLModel


def platform_fk(table: str) -> str:
    """Destino de una FK hacia una tabla de la plataforma, p. ej. platform_fk("tenants")."""
    return f"{table}.id"


class TenantKind(StrEnum):
    INTERNAL = "internal"  # la firma
    CLIENT = "client"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    REVOKED = "revoked"


class SystemRole(StrEnum):
    """Roles del sistema (tenant_id NULL). Cada tenant puede crear roles propios."""

    ADMINISTRADOR = "administrador"
    SOCIO = "socio"
    GERENTE = "gerente"
    SENIOR = "senior"
    ASOCIADO = "asociado"
    CLIENTE = "cliente"


class Permission(StrEnum):
    """Permisos de la tabla permissions que usa este servicio."""

    CLIENTES_CREAR = "clientes.crear"
    CLIENTES_LEER = "clientes.leer"


class Tenant(SQLModel, table=True):
    """Organización: la firma (internal) o un cliente (client)."""

    __tablename__ = "tenants"

    id: UUID = Field(primary_key=True)
    slug: str = Field(max_length=63, unique=True)
    name: str = Field(max_length=200)
    kind: str = Field(max_length=20)
    status: str = Field(max_length=20)
    created_at: datetime = Field(sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(sa_type=DateTime(timezone=True))


class User(SQLModel, table=True):
    """Persona. Entra con Cognito (cognito_sub); sin cognito_sub todavía no ha entrado."""

    __tablename__ = "users"

    id: UUID = Field(primary_key=True)
    cognito_sub: str | None = Field(default=None, max_length=64, unique=True)
    email: str = Field(max_length=320, unique=True)
    full_name: str | None = Field(default=None, max_length=200)
    is_active: bool
    created_at: datetime = Field(sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(sa_type=DateTime(timezone=True))


class Role(SQLModel, table=True):
    """Rol del sistema (tenant_id NULL) o propio de un tenant."""

    __tablename__ = "roles"

    id: UUID = Field(primary_key=True)
    tenant_id: UUID | None = Field(default=None, foreign_key=platform_fk("tenants"))
    code: str = Field(max_length=50)
    name: str = Field(max_length=100)
    created_at: datetime = Field(sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(sa_type=DateTime(timezone=True))


class Membership(SQLModel, table=True):
    """Una persona dentro de un tenant. Sus roles están en membership_roles."""

    __tablename__ = "memberships"

    id: UUID = Field(primary_key=True)
    user_id: UUID = Field(foreign_key=platform_fk("users"))
    tenant_id: UUID = Field(foreign_key=platform_fk("tenants"))
    status: str = Field(max_length=20)
    created_at: datetime = Field(sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(sa_type=DateTime(timezone=True))


class MembershipRole(SQLModel, table=True):
    __tablename__ = "membership_roles"

    membership_id: UUID = Field(primary_key=True, foreign_key=platform_fk("memberships"))
    role_id: UUID = Field(primary_key=True, foreign_key=platform_fk("roles"))


class RolePermission(SQLModel, table=True):
    __tablename__ = "role_permissions"

    role_id: UUID = Field(primary_key=True, foreign_key=platform_fk("roles"))
    permission_code: str = Field(primary_key=True, max_length=100)
