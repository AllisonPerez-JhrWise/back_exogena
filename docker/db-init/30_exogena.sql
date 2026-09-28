-- ════════════════════════════════════════════════════════════════════════
-- Schema de este servicio. En la nube lo crea el administrador (wiseadmin), porque
-- el usuario de las migraciones no puede crear schemas. Las tablas las crea Alembic.
-- ════════════════════════════════════════════════════════════════════════

CREATE SCHEMA exogena AUTHORIZATION exogena_dev;

-- ── PENDIENTE EN LA NUBE: pedir a wiseadmin ──────────────────────────────
-- Las tablas de exogena apuntan con FK a tenants, users y memberships. Crear esas FK exige el
-- permiso REFERENCES, que wiseerp_rw no tiene hoy en la RDS.
GRANT REFERENCES ON public.tenants, public.users, public.memberships TO wiseerp_rw;
