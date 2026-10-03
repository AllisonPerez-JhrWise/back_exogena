"""Lo que este servicio le informa a Identidad (wise-auth).

Identidad decide el acceso con las asignaciones que guarda (quién trabaja en qué
compromiso). Exógena se las informa por su API, nunca escribiendo en sus tablas, y con el
mismo token de quien hace la petición: Identidad valida el token y el permiso igual que con
cualquier otro llamado, y deja su auditoría.

Si Identidad rechaza o no responde, se lanza un error y el service no hace commit: no
queda nada a medias en exógena.
"""

import logging
from typing import Annotated, Protocol
from uuid import UUID

import httpx
from fastapi import Depends
from wise_comun import deps
from wise_comun.deps import CABECERA_ORGANIZACION

from app.core.auth import OrganizationDep
from app.core.config import settings
from app.core.logging import request_id_ctx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(5.0)


class IdentityRejected(Exception):
    """Identidad respondió con un error. `status` es el suyo: 400 rol inválido, 403 sin
    permiso, 404 fuera de alcance o la persona no es miembro, 409 compromiso de otra empresa."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class IdentityUnavailable(Exception):
    """Identidad no respondió (caída, sin red o error interno)."""


class Identity(Protocol):
    def set_engagement_team(
        self, engagement_id: UUID, company_id: UUID, user_id: UUID, roles: list[str]
    ) -> None: ...


class IdentityClient:
    """Llamadas HTTP a Identidad en nombre de quien hace la petición."""

    def __init__(self, token: str, organization_id: UUID):
        self.token = token
        self.organization_id = organization_id

    def set_engagement_team(
        self, engagement_id: UUID, company_id: UUID, user_id: UUID, roles: list[str]
    ) -> None:
        """PUT /compromisos/{id}/equipo/{user_id}: deja a la persona con exactamente esos
        roles de compromiso (socio, gerente…) en ese compromiso."""
        self._put(
            f"/compromisos/{engagement_id}/equipo/{user_id}",
            {"empresa_id": str(company_id), "roles": roles},
        )

    def _put(self, path: str, body: dict) -> None:
        headers = {
            "Authorization": f"Bearer {self.token}",
            CABECERA_ORGANIZACION: str(self.organization_id),
            # El mismo id de petición, para seguirla de punta a punta en los logs
            "X-Request-ID": request_id_ctx.get(),
        }
        url = f"{settings.identidad_url.rstrip('/')}{path}"
        try:
            response = httpx.put(url, json=body, headers=headers, timeout=_TIMEOUT)
        except httpx.HTTPError as exc:
            logger.warning("Identidad no respondió en PUT %s: %s", path, exc)
            raise IdentityUnavailable from exc
        if response.status_code >= 500:
            logger.warning("Identidad respondió %s en PUT %s", response.status_code, path)
            raise IdentityUnavailable
        if response.status_code >= 400:
            try:
                detail = str(response.json().get("detail", ""))
            except ValueError:
                detail = response.text
            raise IdentityRejected(response.status_code, detail)


class DevIdentity:
    """Modo de desarrollo local (AUTH_BYPASS) sin Identidad: no informa nada, solo lo
    deja en el log."""

    def set_engagement_team(
        self, engagement_id: UUID, company_id: UUID, user_id: UUID, roles: list[str]
    ) -> None:
        logger.info(
            "AUTH_BYPASS: no se informa a Identidad el equipo %s de %s (%s)",
            roles,
            engagement_id,
            user_id,
        )


def get_identity(
    token: Annotated[str, Depends(deps.token_actual)], organization: OrganizationDep
) -> Identity:
    return IdentityClient(token, organization)


IdentityDep = Annotated[Identity, Depends(get_identity)]
