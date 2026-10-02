from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.core.config import settings

# create_async_engine todavía no se conecta: la primera consulta abre el pool
engine = create_async_engine(
    settings.async_database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=settings.db_pool_recycle_seconds,
    pool_pre_ping=True,
    echo=settings.db_echo,
    connect_args=settings.db_connect_args,
)

SessionFactory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Una sesión por petición. Los services hacen commit; lo que no se confirme se revierte."""
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]


# ── Contexto de la seguridad por filas (RLS) de la plataforma ─────────────────
# Las tablas de public solo muestran las filas que permiten app.user_id y app.tenant_id.
# Se declaran por transacción (set_config(..., true)): así nunca pasan de una petición a
# otra por el pool de conexiones. Como un commit termina la transacción, se vuelven a
# declarar al empezar la siguiente (evento after_begin).

_DB_CONTEXT = "db_context"
_SET_CONTEXT = text(
    "SELECT set_config('app.user_id', :user_id, true), "
    "set_config('app.tenant_id', :tenant_id, true)"
)


def _context_params(session: Session | AsyncSession) -> dict[str, str] | None:
    return session.info.get(_DB_CONTEXT)


async def set_db_context(
    session: AsyncSession, *, user_id: UUID | None, tenant_id: UUID | None
) -> None:
    """Declara quién consulta y en qué tenant, para esta y las siguientes transacciones."""
    session.info[_DB_CONTEXT] = {
        "user_id": str(user_id) if user_id else "",
        "tenant_id": str(tenant_id) if tenant_id else "",
    }
    await session.execute(_SET_CONTEXT, session.info[_DB_CONTEXT])


@event.listens_for(Session, "after_begin")
def _apply_db_context(session: Session, transaction, connection) -> None:
    params = _context_params(session)
    if params:
        connection.execute(_SET_CONTEXT, params)
