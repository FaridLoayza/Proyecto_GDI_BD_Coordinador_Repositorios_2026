-- Rol de PostgreSQL "admin_cris": CRUD sobre los datos del portal.
--
-- Permisos: SELECT, INSERT, UPDATE y DELETE en todas las tablas del esquema
-- public; uso de secuencias (columnas autoincrementales); EXECUTE de
-- funciones y procedimientos. También para las tablas que se creen después.
-- NO es superusuario: no puede crear, modificar ni borrar tablas (DDL).
--
-- La contraseña no se guarda en el repositorio: se pasa al ejecutar.
-- Es idempotente: si el rol ya existe, actualiza su contraseña y permisos.
--
-- Uso (Windows, como usuario postgres, mínimo 12 caracteres):
--   "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres ^
--     -d bd_coordinador_repositorios -v clave="CLAVE_SEGURA_AQUI" ^
--     -f backend\database\rol_admin_cris.sql

\set ON_ERROR_STOP on

\if :{?clave}
\else
  \echo 'Falta la contraseña. Agregue -v clave="..." al comando psql.'
  \quit
\endif

SELECT set_config('cris.clave_admin', :'clave', false) AS clave_recibida \gset

DO $$
DECLARE
  v_clave TEXT := current_setting('cris.clave_admin');
BEGIN
  IF length(v_clave) < 12 THEN
    RAISE EXCEPTION 'La contraseña de admin_cris debe tener al menos 12 caracteres.';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'admin_cris') THEN
    EXECUTE format('ALTER ROLE admin_cris WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', v_clave);
  ELSE
    EXECUTE format('CREATE ROLE admin_cris WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', v_clave);
  END IF;
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO admin_cris', current_database());
END $$;

SELECT set_config('cris.clave_admin', '', false) AS clave_borrada \gset

GRANT USAGE ON SCHEMA public TO admin_cris;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO admin_cris;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO admin_cris;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO admin_cris;
GRANT EXECUTE ON ALL PROCEDURES IN SCHEMA public TO admin_cris;

-- Tablas, secuencias y rutinas que se creen en el futuro (por el usuario actual).
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO admin_cris;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO admin_cris;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT EXECUTE ON ROUTINES TO admin_cris;

\echo 'Rol admin_cris listo: CRUD sobre todas las tablas del esquema public.'
