from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, text
from sqlmodel import DateTime, Field

from app.shared.models import BaseTable, join_name_parts


class RoleCode(StrEnum):
    """Roles globales: qué puede hacer una persona en el sistema.
    Los papeles dentro de un compromiso (socio, gerente…) NO son roles globales."""

    ADMIN = "admin"
    COLABORADOR = "colaborador"
    USUARIO_CLIENTE = "usuario_cliente"


class AuthProvider(StrEnum):
    """Formas de entrar al sistema. Una persona puede tener varias."""

    PASSWORD = "password"
    GOOGLE = "google"
    MICROSOFT = "microsoft"


class User(BaseTable):
    """Toda persona que el sistema conoce: personal de la firma y usuarios de clientes.
    `can_login` decide si puede entrar (los usuarios de clientes por ahora no)."""

    __tablename__ = "users"
    __table_args__ = (
        # Único solo entre usuarios no borrados: permite volver a crear a alguien eliminado
        Index("ux_users_email", "email", unique=True, postgresql_where=text("NOT is_deleted")),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )

    email: str = Field(max_length=320)
    # Nombre separado como en los documentos colombianos: solo el primero de cada uno es obligatorio
    first_name: str = Field(max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(max_length=100)
    second_last_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    avatar_url: str | None = None
    # Denegado por defecto: el acceso se habilita explícitamente
    can_login: bool = Field(default=False)
    last_login_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))

    @property
    def full_name(self) -> str:
        """Nombre completo para mostrar (no se guarda en la base de datos)."""
        return join_name_parts(
            self.first_name, self.middle_name, self.last_name, self.second_last_name
        )


class Role(BaseTable):
    """Catálogo de roles globales. Se llena con la migración (ver RoleCode)."""

    __tablename__ = "roles"

    code: str = Field(max_length=50, unique=True)
    name: str = Field(max_length=100)
    description: str | None = Field(default=None, max_length=255)


class UserRole(BaseTable):
    """Roles de cada usuario. Una persona puede tener varios (p. ej. colaborador y admin)."""

    __tablename__ = "user_roles"
    __table_args__ = (
        Index(
            "ux_user_roles_user_role",
            "user_id",
            "role_id",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
    )

    user_id: UUID = Field(foreign_key="accounts.users.id", index=True)
    role_id: UUID = Field(foreign_key="accounts.roles.id", index=True)


class UserIdentity(BaseTable):
    """Cómo entra cada persona: con contraseña, Google o Microsoft.
    `subject` es el id que entrega el proveedor (para contraseña, el email)."""

    __tablename__ = "user_identities"
    __table_args__ = (
        # Una misma cuenta de Google/Microsoft solo puede pertenecer a una persona
        Index(
            "ux_user_identities_provider_subject",
            "provider",
            "subject",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
        CheckConstraint("provider IN ('password', 'google', 'microsoft')", name="provider_valid"),
        # Solo la identidad de tipo contraseña guarda un hash, y siempre lo guarda
        CheckConstraint(
            "(provider = 'password') = (password_hash IS NOT NULL)",
            name="password_hash_only_for_password",
        ),
    )

    user_id: UUID = Field(foreign_key="accounts.users.id", index=True)
    provider: str = Field(max_length=20)
    subject: str = Field(max_length=320)
    password_hash: str | None = None
