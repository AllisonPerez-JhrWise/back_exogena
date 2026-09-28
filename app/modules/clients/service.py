from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.database import set_db_context
from app.core.exceptions import ConflictError
from app.modules.clients.models import Client, ClientContact, ClientTaxResponsibility
from app.modules.clients.repository import (
    ClientContactRepository,
    ClientRepository,
    ClientTaxResponsibilityRepository,
)
from app.modules.clients.schemas import ClientCreate, ClientRead, ClientUserIn, ClientUserRead
from app.modules.platform.models import MembershipStatus, SystemRole
from app.modules.platform.repository import PlatformRepository


class PlatformUser(BaseModel):
    id: UUID
    email: str
    full_name: str


class ClientService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.clients = ClientRepository(session)
        self.responsibilities = ClientTaxResponsibilityRepository(session)
        self.contacts = ClientContactRepository(session)
        self.platform = PlatformRepository(session)

    async def create(self, data: ClientCreate, actor: Principal) -> ClientRead:
        """Crea el cliente en UNA transacción (si algo falla, no se guarda nada):
        1. El tenant del cliente en la plataforma, con el contacto principal como
           administrador invitado (función app_crear_organizacion).
        2. Los datos del RUT y sus responsabilidades (exogena).
        3. Una membresía invitada con el rol `cliente` para cada uno de los demás usuarios.
        4. El cargo, teléfono y contacto principal de cada persona (exogena.client_contacts).
        """
        if await self.clients.get_by_nit(data.rut.nit):
            raise ConflictError("A client with this NIT already exists")

        client = Client(
            **data.rut.model_dump(exclude={"tax_responsibilities"}),
            **data.organization.model_dump(),
            created_by=actor.id,
        )

        admin = await self._get_or_create_user(data.primary_contact)
        tenant_id = await self.platform.create_organization(
            slug=f"cliente-{data.rut.nit}", name=client.display_name, admin_id=admin.id
        )
        # De aquí en adelante se trabaja dentro del tenant nuevo (seguridad por filas)
        await set_db_context(self.session, user_id=actor.id, tenant_id=tenant_id)

        client.tenant_id = tenant_id
        client = await self.clients.add(client)
        for code in data.rut.tax_responsibilities:
            await self.responsibilities.add(
                ClientTaxResponsibility(client_id=client.id, code=code, created_by=actor.id)
            )

        client_role = await self.platform.get_system_role(SystemRole.CLIENTE)
        members: list[ClientUserRead] = []
        for item in data.users:
            if item.is_primary_contact:
                user, role = admin, SystemRole.ADMINISTRADOR
                membership = await self.platform.get_membership(admin.id, tenant_id)
                membership_id = membership.id
            else:
                user, role = await self._get_or_create_user(item), SystemRole.CLIENTE
                membership_id = await self.platform.add_membership(
                    user.id, tenant_id, client_role.id, MembershipStatus.INVITED
                )

            contact = await self.contacts.add(
                ClientContact(
                    client_id=client.id,
                    membership_id=membership_id,
                    position=item.position,
                    phone=item.phone,
                    is_primary_contact=item.is_primary_contact,
                    created_by=actor.id,
                )
            )
            members.append(
                ClientUserRead(
                    user_id=user.id,
                    membership_id=membership_id,
                    email=user.email,
                    full_name=user.full_name,
                    role=role,
                    phone=contact.phone,
                    position=contact.position,
                    is_primary_contact=contact.is_primary_contact,
                )
            )

        await self.session.commit()
        return ClientRead(
            **client.model_dump(),
            display_name=client.display_name,
            tax_responsibilities=data.rut.tax_responsibilities,
            users=members,
        )

    async def _get_or_create_user(self, item: ClientUserIn) -> PlatformUser:
        """Usa la persona si ya existe (sin cambiar sus datos); si no, la crea sin acceso.

        Limitación: la seguridad por filas no deja ver a una persona que ya está en otro
        tenant (p. ej. un revisor fiscal de otro cliente). Falta que la plataforma exponga
        una función para buscar por email (tipo app_usuario_por_email)."""
        existing = await self.platform.find_user_by_email(item.email)
        if existing:
            return PlatformUser(
                id=existing.id, email=existing.email, full_name=existing.full_name or ""
            )
        try:
            async with self.session.begin_nested():
                user_id = await self.platform.create_user(item.email, item.full_name)
        except IntegrityError:
            raise ConflictError(
                "This person already exists in another organization. Linking existing "
                "people is not available yet.",
                details={"email": item.email.lower()},
            ) from None
        return PlatformUser(id=user_id, email=item.email.lower(), full_name=item.full_name)
