"""Sesiones de base de datos.

La mecánica —motor, sesión y contexto de Row-Level Security (app.user_id y
app.organization_id, por transacción)— vive en `wise_comun.db` y la comparten todos los
servicios, como en wise-auth. Aquí solo se importa `config`, que registra los ajustes, y
se exponen los nombres que usa el servicio.

La sesión de cada petición es la misma que usa wise-comun para resolver quién llama: así
el contexto de RLS que declara `ContextoActual` aplica a las consultas del servicio.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session
from wise_comun.db import get_db, motor

import app.core.config  # noqa: F401  registra los ajustes antes de abrir ninguna conexión

SessionDep = Annotated[Session, Depends(get_db)]

__all__ = ["SessionDep", "get_db", "motor"]
