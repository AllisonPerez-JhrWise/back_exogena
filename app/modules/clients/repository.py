from app.modules.clients.models import Client, ClientContact, ClientTaxResponsibility
from app.shared.repository import BaseRepository


class ClientRepository(BaseRepository[Client]):
    model = Client

    async def get_by_nit(self, nit: str) -> Client | None:
        result = await self.session.execute(self.base_query().where(Client.nit == nit))
        return result.scalars().first()


class ClientTaxResponsibilityRepository(BaseRepository[ClientTaxResponsibility]):
    model = ClientTaxResponsibility


class ClientContactRepository(BaseRepository[ClientContact]):
    model = ClientContact
