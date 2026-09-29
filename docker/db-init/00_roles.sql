-- ════════════════════════════════════════════════════════════════════════
-- Roles de la base, iguales a los de la RDS (wiseerp). Solo para la base local.
--
--   wiseadmin      dueño de las tablas de la plataforma (en la nube es el administrador)
--   wiseerp_rw     grupo con lectura y escritura (sin cambiar estructura en public)
--   wiseerp_ro     grupo de solo lectura
--   wiseerp_app    usuario con el que corre la app: puede usar las funciones app_*
--                  y la seguridad por filas (RLS) le aplica
--   exogena_dev    equivale a allison_brinez: miembro de wiseerp_rw, dueño del schema
--                  exogena y quien corre las migraciones de este servicio
--
-- Las contraseñas son solo para desarrollo local.
-- ════════════════════════════════════════════════════════════════════════

CREATE ROLE wiseadmin NOLOGIN;
CREATE ROLE wiseerp_rw NOLOGIN;
CREATE ROLE wiseerp_ro NOLOGIN;
CREATE ROLE wiseerp_app LOGIN PASSWORD 'wiseerp_app';
CREATE ROLE exogena_dev LOGIN PASSWORD 'exogena_dev' IN ROLE wiseerp_rw;
