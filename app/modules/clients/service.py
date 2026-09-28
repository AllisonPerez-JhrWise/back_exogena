from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.exceptions import ConflictError
from app.modules.accounts.models import User
from app.modules.accounts.schemas import NewUserData
from app.modules.accounts.service import UserService
from app.modules.clients.models import Client, ClientTaxResponsibility, ClientUser
from app.modules.clients.repository import (
    ClientRepository,
    ClientTaxResponsibilityRepository,
    ClientUserRepository,
)
from app.modules.clients.schemas import ClientCreate, ClientRead, ClientUserRead


class ClientService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.clients = ClientRepository(session)
        self.responsibilities = ClientTaxResponsibilityRepository(session)
        self.client_users = ClientUserRepository(session)
        # Comparte la sesión: todo lo que hace queda en esta misma transacción
        self.users = UserService(session)

    async def create(self, data: ClientCreate, actor: Principal) -> ClientRead:
        """Crea el cliente, sus responsabilidades y sus usuarios en UNA transacción:
        si algo falla, no se guarda nada."""
        if await self.clients.get_by_nit(data.rut.nit):
            raise ConflictError("A client with this NIT already exists")

        client = await self.clients.add(
            Client(
                **data.rut.model_dump(exclude={"tax_responsibilities"}),
                **data.organization.model_dump(),
                created_by=actor.id,
            )
        )
        for code in data.rut.tax_responsibilities:
            await self.responsibilities.add(
                ClientTaxResponsibility(client_id=client.id, code=code, created_by=actor.id)
            )

        members: list[tuple[User, ClientUser]] = []
        for item in data.users:
            # Si el email ya existe (p. ej. un revisor fiscal de otro cliente) se reutiliza
            user = await self.users.get_or_create_client_user(
                NewUserData.model_validate(item.model_dump(include=set(NewUserData.model_fields))),
                actor,
            )
            link = await self.client_users.add(
                ClientUser(
                    client_id=client.id,
                    user_id=user.id,
                    position=item.position,
                    is_primary_contact=item.is_primary_contact,
                    created_by=actor.id,
                )
            )
            members.append((user, link))

        await self.session.commit()
        return self._to_read(client, data.rut.tax_responsibilities, members)

    @staticmethod
    def _to_read(
        client: Client, responsibilities: list[str], members: list[tuple[User, ClientUser]]
    ) -> ClientRead:
        return ClientRead(
            **client.model_dump(),
            display_name=client.display_name,
            tax_responsibilities=responsibilities,
            users=[
                ClientUserRead(
                    user_id=user.id,
                    email=user.email,
                    full_name=user.full_name,
                    phone=user.phone,
                    position=link.position,
                    is_primary_contact=link.is_primary_contact,
                )
                for user, link in members
            ],
        )
