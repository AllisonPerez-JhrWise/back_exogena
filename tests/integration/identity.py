"""Doble de Identidad para las pruebas: responde lo que respondería GET /autorizacion.

Exógena no lee las tablas de Identidad: le pregunta, por wise-comun, quién llama y qué
puede hacer. En las pruebas no hay Identidad, así que este doble guarda en memoria las
personas, las organizaciones y las membresías, y arma la respuesta con la matriz inicial
de la firma (migración 0016 de wise-auth). wise-comun la interpreta igual que en
producción: `exige`, niveles y alcance son los de verdad.

El equipo de cada compromiso (socio y gerente) y las empresas del Cliente se toman de las
tablas de exógena (engagements y company_users): es lo que Identidad tendrá registrado
cuando exógena se lo informe (segmentos 3b y 3c).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session
from wise_comun.deps import SinAcceso

from app.modules.clients.models import CompanyUser
from app.modules.engagements.models import Engagement


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
        answer["compromisos"] = self._team(db, user_id, organization)
        answer["empresas"] = [
            str(c)
            for c in db.scalars(
                select(CompanyUser.company_id).where(
                    CompanyUser.user_id == user_id, CompanyUser.is_deleted.is_(False)
                )
            )
        ]
        return answer

    @staticmethod
    def _team(db: Session, user_id: UUID, organization: UUID) -> dict[str, Any]:
        """Compromisos donde la persona es socio o gerente."""
        team: dict[str, Any] = {}
        rows = db.execute(
            select(Engagement.id, Engagement.company_id, Engagement.partner_user_id).where(
                Engagement.organization_id == organization,
                Engagement.is_deleted.is_(False),
                (Engagement.partner_user_id == user_id) | (Engagement.manager_user_id == user_id),
            )
        )
        for engagement_id, company_id, partner in rows:
            role = SystemRole.SOCIO if partner == user_id else SystemRole.GERENTE
            team[str(engagement_id)] = {
                "empresa_id": str(company_id),
                "roles": [role],
                "formatos": [],
            }
        return team
