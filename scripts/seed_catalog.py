"""Carga el catálogo inicial (obligaciones, tipos de servicio y servicios) en la
organización indicada. Se puede repetir: solo crea lo que falta.

Uso: python -m scripts.seed_catalog --tenant-id <uuid de la firma>
Se conecta con MIGRATION_DATABASE_URL (o DATABASE_URL): el dueño de las tablas de exogena.
En AWS: make aws-seed-catalog tenant=<uuid>
"""

import argparse
import asyncio
import sys
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.modules.catalog.seed import seed_catalog


async def main(tenant_id: UUID) -> int:
    engine = create_async_engine(
        settings.alembic_database_url, connect_args=settings.db_connect_args
    )
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            result = await seed_catalog(session, tenant_id)
            await session.commit()
    except IntegrityError as exc:
        if "tenants" in str(exc.orig):
            print(f"ERROR: no existe el tenant {tenant_id} en public.tenants")
            return 1
        raise
    finally:
        await engine.dispose()
    print(
        f"Catálogo cargado en {tenant_id}: {result.obligations} obligaciones, "
        f"{result.service_types} tipos de servicio y {result.services} servicios nuevos."
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=UUID, required=True, help="UUID de la organización")
    sys.exit(asyncio.run(main(parser.parse_args().tenant_id)))
