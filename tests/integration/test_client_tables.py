"""Reglas de las tablas de usuarios y clientes, verificadas contra PostgreSQL real.
Cada caso intenta romper una regla y comprueba que la base de datos lo impide."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.accounts.models import AuthProvider, User, UserIdentity
from app.modules.clients.models import Client, ClientTaxResponsibility, ClientUser, PersonType


def make_user(email: str, **extra) -> User:
    return User(email=email, first_name=email.split("@")[0], last_name="Prueba", **extra)


def make_client(nit: str = "900123456", **extra) -> Client:
    values = {
        "dv": "4",
        "person_type": PersonType.JURIDICA,
        "legal_name": "Comercializadora Andina SAS",
    }
    return Client(nit=nit, **{**values, **extra})


async def save(session, *objs) -> None:
    session.add_all(objs)
    await session.flush()


async def assert_rejected(session, *objs) -> None:
    """La base de datos debe rechazar estos registros (el savepoint aísla el error)."""
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add_all(objs)
            await session.flush()


async def test_create_client_with_users_in_one_transaction(db_session):
    # El caso del mockup: la empresa, sus responsabilidades y sus 2 usuarios
    client = make_client(
        department_code="11",
        city_code="11001",
        main_activity_code="4719",
        trade_name="Andina Comercial",
    )
    paula = make_user("paula.cordoba@andina.com.co", phone="+57 310 555 4321")
    carlos = make_user("carlos.mejia@revisoria.com.co")
    await save(db_session, client, paula, carlos)
    await save(
        db_session,
        *(ClientTaxResponsibility(client_id=client.id, code=c) for c in ("05", "48", "42")),
        ClientUser(
            client_id=client.id, user_id=paula.id, position="Contadora", is_primary_contact=True
        ),
        ClientUser(client_id=client.id, user_id=carlos.id, position="Revisor fiscal"),
    )
    await db_session.commit()

    assert paula.can_login is False  # los usuarios de clientes no entran por ahora


async def test_nit_is_unique_among_active_clients(db_session):
    first = make_client()
    await save(db_session, first)
    await assert_rejected(db_session, make_client())

    # Con borrado lógico, el NIT se puede volver a usar
    first.is_deleted = True
    await save(db_session, first, make_client())


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
async def test_client_formats_are_enforced(db_session, field, value):
    await assert_rejected(db_session, make_client(**{field: value}))


async def test_only_one_primary_contact_per_client(db_session):
    client, ana, luis = make_client(), make_user("ana@x.co"), make_user("luis@x.co")
    await save(db_session, client, ana, luis)
    await save(db_session, ClientUser(client_id=client.id, user_id=ana.id, is_primary_contact=True))
    await assert_rejected(
        db_session, ClientUser(client_id=client.id, user_id=luis.id, is_primary_contact=True)
    )


async def test_same_person_in_several_clients_with_different_positions(db_session):
    # Un revisor fiscal puede estar en varias empresas, pero no dos veces en la misma
    andina, otra = make_client("900123456"), make_client("800111222")
    carlos = make_user("carlos@revisoria.com.co")
    await save(db_session, andina, otra, carlos)
    await save(
        db_session,
        ClientUser(client_id=andina.id, user_id=carlos.id, position="Revisor fiscal"),
        ClientUser(client_id=otra.id, user_id=carlos.id, position="Revisor fiscal suplente"),
    )
    await assert_rejected(db_session, ClientUser(client_id=andina.id, user_id=carlos.id))


async def test_client_user_requires_existing_user(db_session):
    client = make_client()
    await save(db_session, client)
    await assert_rejected(db_session, ClientUser(client_id=client.id, user_id=client.id))


async def test_user_email_rules(db_session):
    await save(db_session, make_user("ana@x.co"))
    await assert_rejected(db_session, make_user("ana@x.co"))  # repetido
    await assert_rejected(db_session, make_user("Luis@X.co"))  # debe ir en minúsculas


async def test_identity_rules(db_session):
    ana, luis = make_user("ana@x.co"), make_user("luis@x.co")
    await save(db_session, ana, luis)
    await save(
        db_session,
        UserIdentity(user_id=ana.id, provider=AuthProvider.GOOGLE, subject="google-1"),
        UserIdentity(user_id=ana.id, provider=AuthProvider.MICROSOFT, subject="ms-1"),
    )
    # La misma cuenta de Google no puede ser de dos personas
    await assert_rejected(
        db_session, UserIdentity(user_id=luis.id, provider=AuthProvider.GOOGLE, subject="google-1")
    )
    # Contraseña sin hash, o Google con hash: no
    await assert_rejected(
        db_session,
        UserIdentity(user_id=luis.id, provider=AuthProvider.PASSWORD, subject="luis@x.co"),
    )
    await assert_rejected(
        db_session,
        UserIdentity(
            user_id=luis.id, provider=AuthProvider.GOOGLE, subject="g-2", password_hash="x"
        ),
    )
    await assert_rejected(
        db_session, UserIdentity(user_id=luis.id, provider="facebook", subject="fb-1")
    )


async def test_name_depends_on_person_type(db_session):
    # Jurídica sin razón social: no
    await assert_rejected(db_session, make_client(legal_name=None))
    # Natural sin primer apellido: no
    await assert_rejected(
        db_session,
        make_client(person_type=PersonType.NATURAL, legal_name=None, first_name="Juan"),
    )
    # Natural con primer nombre y primer apellido: sí (el resto es opcional)
    natural = make_client(
        "1020304050",
        person_type=PersonType.NATURAL,
        legal_name=None,
        first_name="Juan",
        last_name="Restrepo",
    )
    await save(db_session, natural)
    assert natural.display_name == "Juan Restrepo"
