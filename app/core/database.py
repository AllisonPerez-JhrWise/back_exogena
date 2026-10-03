from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# create_engine todavía no se conecta: la primera consulta abre el pool
engine = create_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=settings.db_pool_recycle_seconds,
    pool_pre_ping=True,
    echo=settings.db_echo,
)

SessionFactory = sessionmaker(engine, expire_on_commit=False, autoflush=False)


def get_session() -> Iterator[Session]:
    """Una sesión por petición. Los services hacen commit; lo que no se confirme se revierte."""
    with SessionFactory() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise


SessionDep = Annotated[Session, Depends(get_session)]


# ── Contexto de la seguridad por filas (RLS) de la plataforma ─────────────────
# Las tablas de public solo muestran las filas que permiten app.user_id y app.tenant_id.
# Se declaran por transacción (set_config(..., true)): así nunca pasan de una petición a
# otra por el pool de conexiones. Como un commit termina la transacción, se vuelven a
# declarar al empezar la siguiente (evento after_begin).
# PROVISIONAL: al pasar los permisos a Identidad se reemplaza por wise_comun.db, que
# declara app.organization_id.

_DB_CONTEXT = "db_context"
_SET_CONTEXT = text(
    "SELECT set_config('app.user_id', :user_id, true), "
    "set_config('app.tenant_id', :tenant_id, true)"
)


def set_db_context(session: Session, *, user_id: UUID | None, tenant_id: UUID | None) -> None:
    """Declara quién consulta y en qué tenant, para esta y las siguientes transacciones."""
    session.info[_DB_CONTEXT] = {
        "user_id": str(user_id) if user_id else "",
        "tenant_id": str(tenant_id) if tenant_id else "",
    }
    session.execute(_SET_CONTEXT, session.info[_DB_CONTEXT])


@event.listens_for(Session, "after_begin")
def _apply_db_context(session: Session, transaction, connection) -> None:
    params = session.info.get(_DB_CONTEXT)
    if params:
        connection.execute(_SET_CONTEXT, params)
