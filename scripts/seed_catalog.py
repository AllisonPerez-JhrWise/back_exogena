"""Carga el catálogo inicial (obligaciones, tipos de servicio y servicios) en la
organización indicada. Se puede repetir: solo crea lo que falta.

Uso: python -m scripts.seed_catalog --tenant-id <uuid de la firma>
Se conecta con DB_ADMIN_USER (o DB_USER): el dueño de las tablas de exogena.
En AWS: make aws-seed-catalog tenant=<uuid>
"""

import argparse
import sys
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.catalog.seed import seed_catalog


def main(tenant_id: UUID) -> int:
    engine = create_engine(settings.admin_database_url)
    try:
        with Session(engine, expire_on_commit=False) as session:
            result = seed_catalog(session, tenant_id)
            session.commit()
    except IntegrityError as exc:
        if "tenants" in str(exc.orig):
            print(f"ERROR: no existe el tenant {tenant_id} en public.tenants")
            return 1
        raise
    finally:
        engine.dispose()
    print(
        f"Catálogo cargado en {tenant_id}: {result.obligations} obligaciones, "
        f"{result.service_types} tipos de servicio y {result.services} servicios nuevos."
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=UUID, required=True, help="UUID de la organización")
    sys.exit(main(parser.parse_args().tenant_id))
