-- Migración: el Scopus Author ID pasa a ser opcional.
--
-- Motivo: el ORCID ahora se verifica con login OAuth y el Scopus ID se
-- autocompleta desde los identificadores externos públicos de ese ORCID.
-- Un investigador puede no tener Scopus ID (Elsevier solo lo asigna cuando
-- indexa una publicación suya en Scopus), así que la columna debe aceptar NULL.
--
-- Se ejecuta UNA vez contra una base ya instalada. Es idempotente: si se
-- vuelve a ejecutar no produce errores ni cambios adicionales.
-- Las instalaciones nuevas (instalar_bd.py) ya crean las tablas así.
--
-- Ejemplo (Windows):
--   "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres ^
--     -d bd_coordinador_repositorios -f backend\database\migracion_scopus_opcional.sql

BEGIN;

ALTER TABLE formato_investigador
  ALTER COLUMN scopus_id DROP NOT NULL;
ALTER TABLE formato_investigador
  DROP CONSTRAINT IF EXISTS ck_formato_inv_scopus;
ALTER TABLE formato_investigador
  ADD CONSTRAINT ck_formato_inv_scopus
  CHECK (scopus_id IS NULL OR scopus_id > 0);

ALTER TABLE solicitud_investigador
  ALTER COLUMN scopus_id DROP NOT NULL;
ALTER TABLE solicitud_investigador
  DROP CONSTRAINT IF EXISTS ck_solicitud_investigador_scopus;
ALTER TABLE solicitud_investigador
  ADD CONSTRAINT ck_solicitud_investigador_scopus
  CHECK (scopus_id IS NULL OR scopus_id > 0);

COMMIT;
