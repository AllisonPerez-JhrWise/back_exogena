-- ════════════════════════════════════════════════════════════════════════
-- Schema de este servicio. En la nube lo crea el administrador (wiseadmin), porque
-- el usuario de las migraciones no puede crear schemas. Las tablas las crea Alembic.
-- Nuestras tablas guardan los IDs de Identidad sin FK, así que no necesitan permisos
-- sobre las tablas de la plataforma.
-- ════════════════════════════════════════════════════════════════════════

CREATE SCHEMA exogena AUTHORIZATION exogena_dev;
