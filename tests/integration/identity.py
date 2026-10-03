"""Doble de Identidad para las pruebas: responde lo que respondería GET /autorizacion.

Exógena no lee las tablas de Identidad: le pregunta, por wise-comun, quién llama y qué
puede hacer. En las pruebas no hay Identidad, así que este doble guarda en memoria las
personas, las organizaciones y las membresías, y arma la respuesta con la matriz inicial
de la firma (migración 0016 de wise-auth). wise-comun la interpreta igual que en
producción: `exige`, niveles y alcance son los de verdad.

El equipo de cada compromiso es el que exógena le informa (PUT /compromisos/{id}/equipo,
con `client_for`), como en producción. Las empresas del Cliente se toman de company_users
con user_id: es lo que Identidad tendrá cuando a esa persona le asignen sus empresas
(invitar a los usuarios del cliente no es de este servicio).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session
from wise_comun.deps import SinAcceso

from app.core.identity import IdentityRejected, IdentityUnavailable
from app.modules.clients.models import CompanyUser


class SystemRole(StrEnum):
    ADMINISTRADOR = "administrador"
    SOCIO = "socio"
    GERENTE = "gerente"
    SENIOR = "senior"
    ASOCIADO = "asociado"
    CLIENTE = "cliente"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


_SI, _CONSULTA = "si", "consulta"
# Matriz inicial de la firma (solo los permisos que usa exógena): rol -> (ámbito, tipo, permisos)
MATRIX: dict[str, tuple[str, str, dict[str, str]]] = {
    "administrador": (
        "general",
        "interno",
        {"clientes.crear": _SI, "clientes.estado.cambiar": _SI},
    ),
    "socio": ("compromiso", "interno", {"clientes.crear": _CONSULTA}),
    "gerente": ("compromiso", "interno", {"clientes.crear": _CONSULTA}),
    "senior": ("compromiso", "interno", {"clientes.crear": _CONSULTA}),
    "asociado": ("compromiso", "interno", {"clientes.crear": _CONSULTA}),
    "cliente": ("general", "externo", {"clientes.crear": _CONSULTA}),
}
GENERAL_ROLES = {code for code, (scope, _, _) in MATRIX.items() if scope == "general"}


def token_for(user_id: UUID) -> str:
    return f"token-{user_id}"


@dataclass
class FakeIdentity:
    people: dict[UUID, tuple[str, str]] = field(default_factory=dict)  # id -> (correo, nombre)
    # (persona, organización) -> (rol general o None, estado)
    memberships: dict[tuple[UUID, UUID], tuple[SystemRole, MembershipStatus]] = field(
        default_factory=dict
    )
    # (compromiso, persona) -> (organización, empresa, roles): compromiso_equipo
    team: dict[tuple[UUID, UUID], tuple[UUID, UUID, list[str]]] = field(default_factory=dict)
    # Para probar qué pasa si Identidad se cae
    unavailable: bool = False

    # ── Lo que antes se escribía en las tablas de public ──

    def user(self, email: str, full_name: str = "Persona Prueba") -> UUID:
        user_id = uuid4()
        self.people[user_id] = (email.lower(), full_name)
        return user_id

    def tenant(self, slug: str) -> UUID:
        """Una organización (la firma)."""
        return uuid4()

    def member(
        self,
        user_id: UUID,
        organization_id: UUID,
        role: SystemRole,
        status: MembershipStatus = MembershipStatus.ACTIVE,
    ) -> None:
        self.memberships[(user_id, organization_id)] = (role, status)

    def is_active_member(self, user_id: UUID, organization_id: UUID) -> bool:
        _, status = self.memberships.get((user_id, organization_id), (None, None))
        return status == MembershipStatus.ACTIVE

    def client_for(self, organization_id: UUID) -> FakeIdentityClient:
        return FakeIdentityClient(self, organization_id)

    def knows(self, token: str) -> bool:
        return any(token == token_for(u) for u in self.people)

    # ── GET /autorizacion ──

    def resolve(
        self, token: str, claims: dict, organization: UUID | None, db: Session
    ) -> dict[str, Any]:
        user_id = next(u for u in self.people if token_for(u) == token)
        email, name = self.people[user_id]
        answer: dict[str, Any] = {
            "usuario": {"id": str(user_id), "email": email, "nombre": name},
            "organizacion": None,
            "roles": {},
            "generales": [],
            "compromisos": {},
            "empresas": [],
            "consentimiento_pendiente": None,
        }
        if organization is None:
            return answer
        role, status = self.memberships.get((user_id, organization), (None, None))
        if status != MembershipStatus.ACTIVE:
            raise SinAcceso  # sin membresía activa en esa organización: 403

        answer["organizacion"] = {"id": str(organization), "tipo": "firma"}
        answer["roles"] = {
            code: {"ambito": scope, "tipo": kind, "permisos": perms}
            for code, (scope, kind, perms) in MATRIX.items()
        }
        answer["generales"] = [role] if role in GENERAL_ROLES else []
        answer["compromisos"] = {
            str(engagement): {"empresa_id": str(company), "roles": roles, "formatos": []}
            for (engagement, person), (org, company, roles) in self.team.items()
            if person == user_id and org == organization and roles
        }
        answer["empresas"] = [
            str(c)
            for c in db.scalars(
                select(CompanyUser.company_id).where(
                    CompanyUser.user_id == user_id, CompanyUser.is_deleted.is_(False)
                )
            )
        ]
        return answer


@dataclass
class FakeIdentityClient:
    """Lo que exógena le informa a Identidad, en nombre de quien hace la petición."""

    identity: FakeIdentity
    organization_id: UUID
    calls: list[tuple[UUID, UUID, list[str]]] = field(default_factory=list)

    def set_engagement_team(
        self, engagement_id: UUID, company_id: UUID, user_id: UUID, roles: list[str]
    ) -> None:
        if self.identity.unavailable:
            raise IdentityUnavailable
        # Como Identidad: la persona tiene que ser miembro de la organización (si no, 404)
        if not self.identity.is_active_member(user_id, self.organization_id):
            raise IdentityRejected(404, "esa persona no es miembro de la organizacion")
        self.identity.team[(engagement_id, user_id)] = (self.organization_id, company_id, roles)
