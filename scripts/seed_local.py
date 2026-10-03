"""SOLO LOCAL: deja la base local lista para probar la API.

Carga el catálogo inicial en la firma de prueba (DEV_ORGANIZATION_ID). Las personas,
las organizaciones y los permisos son de Identidad: en local, con AUTH_BYPASS=true, se
actúa como Administrador de esa firma sin token (ver app/core/dev_access.py).

Uso: make seed
"""

import sys
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Environment, settings
from app.modules.catalog.seed import seed_catalog

# ID fijo de la firma de prueba: el DEV_ORGANIZATION_ID de .env_example
FIRM_ID = UUID("00000000-0000-4000-8000-00000000f1a0")


def main() -> int:
    if settings.environment != Environment.LOCAL:
        print("ERROR: este script solo corre con ENVIRONMENT=local")
        return 1

    firm_id = settings.dev_organization_id or FIRM_ID
    engine = create_engine(settings.admin_database_url)
    with Session(engine, expire_on_commit=False) as session:
        result = seed_catalog(session, firm_id, settings.dev_user_id)
        session.commit()
    engine.dispose()

    print(
        f"OK - Catálogo de la firma de prueba ({firm_id}): {result.obligations} obligaciones, "
        f"{result.service_types} tipos de servicio y {result.services} servicios nuevos.\n\n"
        f"En .env debe estar: DEV_ORGANIZATION_ID={firm_id}\n"
        "Con AUTH_BYPASS=true la API funciona sin token: en http://localhost:8000/docs se\n"
        "actúa como Administrador de esa firma."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
