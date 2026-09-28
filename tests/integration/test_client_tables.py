"""Reglas de las tablas de clientes, verificadas contra PostgreSQL real.
Cada caso intenta romper una regla y comprueba que la base de datos lo impide."""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.clients.models import Client, ClientContact, ClientTaxResponsibility, PersonType
from app.modules.platform.models import SystemRole, TenantKind


def make_client(tenant_id, nit: str = "900123456", **extra) -> Client:
    values = {
        "dv": "4",
        "person_type": PersonType.JURIDICA,
        "legal_name": "Comercializadora Andina SAS",
    }
    return Client(tenant_id=tenant_id, nit=nit, **{**values, **extra})


async def save(session, *objs) -> None:
    session.add_all(objs)
    await session.flush()


async def assert_rejected(session, *objs) -> None:
    """La base de datos debe rechazar estos registros (el savepoint aísla el error)."""
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add_all(objs)
            await session.flush()


@pytest.fixture
def tenant(platform):
    """Crea un tenant de cliente en la plataforma."""

    async def _tenant(slug: str = "cliente-andina"):
        return await platform.tenant(slug, TenantKind.CLIENT)

    return _tenant


@pytest.fixture
def membership(platform):
    """Crea una persona con membresía en el tenant y devuelve el id de la membresía."""

    async def _membership(tenant_id, email: str):
        user_id = await platform.user(email)
        return await platform.member(user_id, tenant_id, SystemRole.CLIENTE)

    return _membership


async def test_client_with_responsibilities_and_contacts(db_session, tenant, membership):
    tenant_id = await tenant()
    client = make_client(tenant_id, department_code="11", city_code="11001")
    await save(db_session, client)
    paula = await membership(tenant_id, "paula@andina.com.co")
    carlos = await membership(tenant_id, "carlos@revisoria.com.co")
    await save(
        db_session,
        *(ClientTaxResponsibility(client_id=client.id, code=c) for c in ("05", "48", "42")),
        ClientContact(
            client_id=client.id, membership_id=paula, position="Contadora", is_primary_contact=True
        ),
        ClientContact(client_id=client.id, membership_id=carlos, position="Revisor fiscal"),
    )


async def test_client_requires_existing_tenant(db_session):
    await assert_rejected(db_session, make_client(uuid4()))


async def test_one_client_per_tenant(db_session, tenant):
    tenant_id = await tenant()
    await save(db_session, make_client(tenant_id))
    await assert_rejected(db_session, make_client(tenant_id, nit="800111222"))


async def test_nit_is_unique_among_active_clients(db_session, tenant):
    first = make_client(await tenant("cliente-1"))
    await save(db_session, first)
    await assert_rejected(db_session, make_client(await tenant("cliente-2")))

    # Con borrado lógico, el NIT se puede volver a usar
    first.is_deleted = True
    await save(db_session, first, make_client(await tenant("cliente-3")))


@pytest.mark.parametrize(
    "field, value",
    [
        ("nit", "900-123"),
        ("dv", "X"),
        ("person_type", "empresa"),
        ("department_code", "1"),
        ("city_code", "BOGOT"),
        ("main_activity_code", "47"),
    ],
)
async def test_client_formats_are_enforced(db_session, tenant, field, value):
    await assert_rejected(db_session, make_client(await tenant(), **{field: value}))


async def test_only_one_primary_contact_per_client(db_session, tenant, membership):
    tenant_id = await tenant()
    client = make_client(tenant_id)
    await save(db_session, client)
    ana = await membership(tenant_id, "ana@x.co")
    luis = await membership(tenant_id, "luis@x.co")
    await save(
        db_session, ClientContact(client_id=client.id, membership_id=ana, is_primary_contact=True)
    )
    await assert_rejected(
        db_session, ClientContact(client_id=client.id, membership_id=luis, is_primary_contact=True)
    )


async def test_one_contact_per_membership(db_session, tenant, membership):
    tenant_id = await tenant()
    client = make_client(tenant_id)
    await save(db_session, client)
    ana = await membership(tenant_id, "ana@x.co")
    await save(db_session, ClientContact(client_id=client.id, membership_id=ana))
    await assert_rejected(db_session, ClientContact(client_id=client.id, membership_id=ana))


async def test_contact_requires_existing_membership(db_session, tenant):
    client = make_client(await tenant())
    await save(db_session, client)
    await assert_rejected(db_session, ClientContact(client_id=client.id, membership_id=uuid4()))


async def test_name_depends_on_person_type(db_session, tenant):
    # Jurídica sin razón social: no
    await assert_rejected(db_session, make_client(await tenant("c-1"), legal_name=None))
    # Natural sin primer apellido: no
    await assert_rejected(
        db_session,
        make_client(
            await tenant("c-2"), person_type=PersonType.NATURAL, legal_name=None, first_name="Juan"
        ),
    )
    # Natural con primer nombre y primer apellido: sí (el resto es opcional)
    natural = make_client(
        await tenant("c-3"),
        "1020304050",
        person_type=PersonType.NATURAL,
        legal_name=None,
        first_name="Juan",
        last_name="Restrepo",
    )
    await save(db_session, natural)
    assert natural.display_name == "Juan Restrepo"
