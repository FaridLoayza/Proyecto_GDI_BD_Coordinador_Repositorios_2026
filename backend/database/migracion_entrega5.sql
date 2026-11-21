-- Migración de la entrega 5 (Portal CRIS v1.2.0).
--
-- Para una base YA instalada con una versión anterior. Es idempotente.
--   * Borrado lógico en investigador, patente e historico (activo, fecha_baja,
--     motivo_baja) con triggers trg_*_baja.
--   * sp_eliminar_* pasan a dar de baja; nuevos sp_reactivar_*.
--   * Los 15 reportes como procedimientos sp_reporte_01 ... sp_reporte_15.
--   * Procedimientos del panel de administrador sp_admin_insertar/actualizar/eliminar.
--   * sp_generar_reporte e indicadores consideran solo registros activos.
-- No agrega datos de prueba: para probar con más datos, instale una base nueva
-- con base_datos_repositorio.sql (o PortalCRIS.exe --instalar-bd).
--
-- Uso (Windows):
--   "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres ^
--     -d bd_coordinador_repositorios -f backend\database\migracion_entrega5.sql

BEGIN;

ALTER TABLE investigador
  ADD COLUMN IF NOT EXISTS activo BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS fecha_baja TIMESTAMPTZ DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS motivo_baja VARCHAR(255) DEFAULT NULL;
ALTER TABLE investigador DROP CONSTRAINT IF EXISTS ck_investigador_baja;
ALTER TABLE investigador ADD CONSTRAINT ck_investigador_baja CHECK (activo OR fecha_baja IS NOT NULL);

ALTER TABLE patente
  ADD COLUMN IF NOT EXISTS activo BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS fecha_baja TIMESTAMPTZ DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS motivo_baja VARCHAR(255) DEFAULT NULL;
ALTER TABLE patente DROP CONSTRAINT IF EXISTS ck_patente_baja;
ALTER TABLE patente ADD CONSTRAINT ck_patente_baja CHECK (activo OR fecha_baja IS NOT NULL);

ALTER TABLE historico
  ADD COLUMN IF NOT EXISTS activo BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS fecha_baja TIMESTAMPTZ DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS motivo_baja VARCHAR(255) DEFAULT NULL;
ALTER TABLE historico DROP CONSTRAINT IF EXISTS ck_historico_baja;
ALTER TABLE historico ADD CONSTRAINT ck_historico_baja CHECK (activo OR fecha_baja IS NOT NULL);

-- Los procedimientos de borrado cambian de firma (agregan el motivo): se quitan
-- las versiones anteriores para evitar llamadas ambiguas.
DROP PROCEDURE IF EXISTS sp_eliminar_investigador(BIGINT);
DROP PROCEDURE IF EXISTS sp_eliminar_patente(VARCHAR);
DROP PROCEDURE IF EXISTS sp_eliminar_historico(UUID);

CREATE OR REPLACE FUNCTION fn_historico_synced_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  -- Dar de baja o reactivar (borrado lógico) no cuenta como re-sincronización.
  IF NEW.activo IS NOT DISTINCT FROM OLD.activo THEN
    NEW.synced_at := CURRENT_TIMESTAMP;
  END IF;
  RETURN NEW;
END; $$;

CREATE OR REPLACE PROCEDURE sp_generar_reporte(p_fecha DATE, p_coordinador BIGINT)
LANGUAGE plpgsql AS $$
DECLARE
  v_dia  SMALLINT := EXTRACT(DAY   FROM p_fecha);
  v_mes  SMALLINT := EXTRACT(MONTH FROM p_fecha);
  v_anio SMALLINT := EXTRACT(YEAR  FROM p_fecha);
BEGIN
  IF NOT EXISTS (SELECT 1 FROM coordinador_repositorios
                 WHERE codigo_ucsm = p_coordinador AND fecha_retiro IS NULL) THEN
    RAISE EXCEPTION 'El coordinador % no existe o ya fue retirado', p_coordinador;
  END IF;

  INSERT INTO reporte (dia, mes, anio, codigo_ucsm_coordinador)
  VALUES (v_dia, v_mes, v_anio, p_coordinador)
  ON CONFLICT (dia, mes, anio) DO UPDATE
    SET codigo_ucsm_coordinador = EXCLUDED.codigo_ucsm_coordinador;

  DELETE FROM total_publicaciones     WHERE dia = v_dia AND mes = v_mes AND anio = v_anio;
  DELETE FROM total_investigadores    WHERE dia = v_dia AND mes = v_mes AND anio = v_anio;
  DELETE FROM cantidad_escuelas_prof  WHERE dia = v_dia AND mes = v_mes AND anio = v_anio;
  DELETE FROM cantidad_ods_vinculados WHERE dia = v_dia AND mes = v_mes AND anio = v_anio;
  DELETE FROM top_escu_invest         WHERE dia = v_dia AND mes = v_mes AND anio = v_anio;
  DELETE FROM rankings_ods            WHERE dia = v_dia AND mes = v_mes AND anio = v_anio;
  DELETE FROM distribuciones_ods      WHERE dia = v_dia AND mes = v_mes AND anio = v_anio;
  DELETE FROM tops_escuelas           WHERE dia = v_dia AND mes = v_mes AND anio = v_anio;

  INSERT INTO total_publicaciones (dia, mes, anio, publicacion)
    SELECT DISTINCT v_dia, v_mes, v_anio, h.title FROM historico h WHERE h.activo;

  INSERT INTO total_investigadores (dia, mes, anio, investigador)
    SELECT v_dia, v_mes, v_anio, i.codigo_ucsm FROM investigador i WHERE i.activo;

  INSERT INTO cantidad_escuelas_prof (dia, mes, anio, escuelas_prof)
    SELECT DISTINCT v_dia, v_mes, v_anio, i.escuela_profesional FROM investigador i WHERE i.activo;

  INSERT INTO cantidad_ods_vinculados (dia, mes, anio, ods_vinc)
    SELECT DISTINCT v_dia, v_mes, v_anio, (substring(o.ods FROM '^ODS ([0-9]+):'))::SMALLINT
    FROM formato_inv_ods o;

  -- Top 5 de ODS: "1: ODS 9"
  WITH conteo AS (
    SELECT substring(ods FROM '^ODS [0-9]+') AS ods_nombre, COUNT(*) AS n
    FROM formato_inv_ods GROUP BY 1 ORDER BY n DESC, 1 LIMIT 5)
  INSERT INTO rankings_ods (dia, mes, anio, ranking_ods)
    SELECT v_dia, v_mes, v_anio,
           (ROW_NUMBER() OVER (ORDER BY n DESC, ods_nombre))::TEXT || ': ' || ods_nombre
    FROM conteo;

  -- Distribucion porcentual: "ODS 9: 45%"
  WITH conteo AS (
    SELECT substring(ods FROM '^ODS [0-9]+') AS ods_nombre, COUNT(*) AS n
    FROM formato_inv_ods GROUP BY 1)
  INSERT INTO distribuciones_ods (dia, mes, anio, distribucion_ods)
    SELECT v_dia, v_mes, v_anio,
           ods_nombre || ': ' || (ROUND(100.0 * n / SUM(n) OVER (), 0))::INT::TEXT || '%'
    FROM conteo;

  -- Top 3 de escuelas con mas investigadores
  INSERT INTO tops_escuelas (dia, mes, anio, top_escuelas)
    SELECT v_dia, v_mes, v_anio, t.escuela
    FROM (SELECT escuela_profesional AS escuela
          FROM investigador
          WHERE activo
          GROUP BY escuela_profesional
          ORDER BY COUNT(*) DESC, escuela_profesional
          LIMIT 3) t;

  -- Investigador con mas publicaciones por escuela (cruza autores con persona por nombre)
  INSERT INTO top_escu_invest (dia, mes, anio, top_escu_invest)
    SELECT v_dia, v_mes, v_anio, x.nombre || ' (' || x.escuela || ')'
    FROM (
      SELECT DISTINCT ON (i.escuela_profesional)
             pe.apellido_paterno || ' ' || pe.apellido_materno || ', ' || pe.nombres AS nombre,
             i.escuela_profesional AS escuela
      FROM investigador i
      JOIN persona pe ON pe.dni = i.dni
      JOIN historico_contributors hc
           ON hc.contributors = pe.apellido_paterno || ' ' || pe.apellido_materno || ', ' || pe.nombres
      WHERE i.activo
      GROUP BY i.escuela_profesional, i.codigo_ucsm,
               pe.apellido_paterno, pe.apellido_materno, pe.nombres
      ORDER BY i.escuela_profesional, COUNT(*) DESC, i.codigo_ucsm
    ) x;
END; $$;

CREATE OR REPLACE PROCEDURE sp_crear_solicitud_investigador(
  p_dni VARCHAR, p_codigo_ucsm BIGINT, p_correo VARCHAR,
  p_password_hash VARCHAR, p_datos JSONB
)
LANGUAGE plpgsql AS $$
DECLARE
  v_cuenta_id BIGINT;
  v_solicitud_id BIGINT;
  v_version_id BIGINT;
BEGIN
  IF p_dni !~ '^[0-9]{8}$'
     OR p_codigo_ucsm NOT BETWEEN 1000000000 AND 9999999999 THEN
    RAISE EXCEPTION 'El DNI o el código institucional no tiene el formato esperado.';
  END IF;
  IF COALESCE(btrim(p_correo), '') = ''
     OR p_correo !~ '^[^@]+@[^@]+\.[^@]+$'
     OR lower(p_datos ->> 'correo') IS DISTINCT FROM lower(btrim(p_correo)) THEN
    RAISE EXCEPTION 'El correo de la cuenta y del formulario no coincide.';
  END IF;
  IF COALESCE(p_password_hash, '') NOT LIKE 'pbkdf2_sha256$%' THEN
    RAISE EXCEPTION 'La contraseña debe recibirse como hash PBKDF2.';
  END IF;
  IF p_datos IS NULL OR jsonb_typeof(p_datos) <> 'object'
     OR p_datos ->> 'dni' IS DISTINCT FROM p_dni
     OR p_datos ->> 'codigo_ucsm' IS DISTINCT FROM p_codigo_ucsm::TEXT THEN
    RAISE EXCEPTION 'Complete los datos de identificación de la solicitud.';
  END IF;
  IF jsonb_typeof(p_datos -> 'ods') IS DISTINCT FROM 'array'
     OR jsonb_typeof(p_datos -> 'intereses') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'Los ODS y los intereses deben enviarse como listas.';
  END IF;
  IF jsonb_array_length(p_datos -> 'ods') = 0
     OR jsonb_array_length(p_datos -> 'intereses') = 0 THEN
    RAISE EXCEPTION 'Complete los datos, ODS e intereses de la solicitud.';
  END IF;
  IF EXISTS (
    SELECT 1
      FROM investigador i
      JOIN formato_investigador fi ON fi.codigo_ucsm = i.codigo_ucsm
     WHERE i.dni = p_dni
        OR i.codigo_ucsm = p_codigo_ucsm
        OR lower(i.correo_elec) = lower(btrim(p_correo))
        OR fi.codigo_orcid = p_datos ->> 'orcid'
        OR fi.scopus_id::TEXT = p_datos ->> 'scopus_id'
        OR lower(fi.link_cti_vitae) = lower(p_datos ->> 'link_cti')
  ) THEN
    RAISE EXCEPTION 'Ya existe un perfil de investigador con esos datos.';
  END IF;

  INSERT INTO cuenta_investigador
    (dni, codigo_ucsm, correo_elec, password_hash)
  VALUES (p_dni, p_codigo_ucsm, lower(btrim(p_correo)), p_password_hash)
  RETURNING id INTO v_cuenta_id;

  INSERT INTO solicitud_investigador (
    cuenta_investigador_id, nombres, apellido_paterno, apellido_materno,
    genero, fecha_nacimiento, escuela_profesional, n_celular,
    codigo_orcid, scopus_id, link_cti_vitae, resumen_academico,
    foto_referencia
  )
  VALUES (
    v_cuenta_id, p_datos ->> 'nombres', p_datos ->> 'apellido_paterno',
    p_datos ->> 'apellido_materno', p_datos ->> 'genero',
    (p_datos ->> 'fecha_nacimiento')::DATE, p_datos ->> 'escuela',
    (p_datos ->> 'celular')::INTEGER, p_datos ->> 'orcid',
    (p_datos ->> 'scopus_id')::BIGINT, p_datos ->> 'link_cti',
    p_datos ->> 'resumen', p_datos ->> 'foto'
  )
  RETURNING id INTO v_solicitud_id;

  INSERT INTO solicitud_investigador_ods (solicitud_id, ods)
    SELECT v_solicitud_id, x.valor
      FROM jsonb_array_elements_text(p_datos -> 'ods') AS x(valor);
  INSERT INTO solicitud_investigador_interes (solicitud_id, interes)
    SELECT v_solicitud_id, x.valor
      FROM jsonb_array_elements_text(p_datos -> 'intereses') AS x(valor);

  INSERT INTO solicitud_investigador_version
    (solicitud_id, numero_version, datos_snapshot, version_esquema)
  VALUES (v_solicitud_id, 1, p_datos, '1')
  RETURNING id INTO v_version_id;
END; $$;

CREATE OR REPLACE PROCEDURE sp_actualizar_solicitud_investigador(
  p_id BIGINT, p_dni VARCHAR, p_codigo_ucsm BIGINT,
  p_correo VARCHAR, p_datos JSONB
)
LANGUAGE plpgsql AS $$
DECLARE
  v_solicitud solicitud_investigador%ROWTYPE;
  v_dni CHAR(8);
  v_codigo_ucsm BIGINT;
  v_cuenta_id BIGINT;
BEGIN
  SELECT * INTO v_solicitud
    FROM solicitud_investigador
   WHERE id = p_id
   FOR UPDATE;
  IF NOT FOUND OR v_solicitud.estado <> 'observada' THEN
    RAISE EXCEPTION 'Solo se pueden corregir solicitudes observadas.';
  END IF;

  SELECT c.dni, c.codigo_ucsm, c.id
    INTO v_dni, v_codigo_ucsm, v_cuenta_id
    FROM cuenta_investigador c
   WHERE c.id = v_solicitud.cuenta_investigador_id;

  -- El DNI y el codigo UCSM se pueden corregir solo mientras la solicitud
  -- esta observada (por ejemplo, cuando el coordinador indica que el
  -- codigo UCSM no es valido). Se valida que el nuevo valor no este en uso
  -- por otra cuenta antes de aplicarlo.
  IF p_dni <> v_dni AND EXISTS (
    SELECT 1 FROM cuenta_investigador WHERE dni = p_dni AND id <> v_cuenta_id
  ) THEN
    RAISE EXCEPTION 'Ese DNI ya esta registrado en otra cuenta.';
  END IF;
  IF p_codigo_ucsm <> v_codigo_ucsm AND EXISTS (
    SELECT 1 FROM cuenta_investigador
     WHERE codigo_ucsm = p_codigo_ucsm AND id <> v_cuenta_id
  ) THEN
    RAISE EXCEPTION 'Ese código institucional ya está registrado en otra cuenta.';
  END IF;

  IF p_datos IS NULL OR jsonb_typeof(p_datos) <> 'object'
     OR p_datos ->> 'dni' IS DISTINCT FROM p_dni
     OR p_datos ->> 'codigo_ucsm' IS DISTINCT FROM p_codigo_ucsm::TEXT
     OR lower(p_datos ->> 'correo') IS DISTINCT FROM lower(btrim(p_correo)) THEN
    RAISE EXCEPTION 'Los datos de identificación o correo no coinciden.';
  END IF;
  IF jsonb_typeof(p_datos -> 'ods') IS DISTINCT FROM 'array'
     OR jsonb_typeof(p_datos -> 'intereses') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'Los ODS y los intereses deben enviarse como listas.';
  END IF;
  IF jsonb_array_length(p_datos -> 'ods') = 0
     OR jsonb_array_length(p_datos -> 'intereses') = 0 THEN
    RAISE EXCEPTION 'Los datos corregidos no son consistentes o están incompletos.';
  END IF;

  UPDATE cuenta_investigador
     SET dni = p_dni,
         codigo_ucsm = p_codigo_ucsm,
         correo_elec = lower(btrim(p_correo)),
         actualizado_en = CURRENT_TIMESTAMP
   WHERE id = v_cuenta_id;
  UPDATE solicitud_investigador
     SET nombres = p_datos ->> 'nombres',
         apellido_paterno = p_datos ->> 'apellido_paterno',
         apellido_materno = p_datos ->> 'apellido_materno',
         genero = p_datos ->> 'genero',
         fecha_nacimiento = (p_datos ->> 'fecha_nacimiento')::DATE,
         escuela_profesional = p_datos ->> 'escuela',
         n_celular = (p_datos ->> 'celular')::INTEGER,
         codigo_orcid = p_datos ->> 'orcid',
         scopus_id = (p_datos ->> 'scopus_id')::BIGINT,
         link_cti_vitae = p_datos ->> 'link_cti',
         resumen_academico = p_datos ->> 'resumen',
         foto_referencia = p_datos ->> 'foto',
         version_actual = version_actual + 1,
         estado = 'pendiente_revision',
         enviada_en = CURRENT_TIMESTAMP,
         actualizado_en = CURRENT_TIMESTAMP
   WHERE id = p_id;

  DELETE FROM solicitud_investigador_ods WHERE solicitud_id = p_id;
  INSERT INTO solicitud_investigador_ods (solicitud_id, ods)
    SELECT p_id, x.valor
      FROM jsonb_array_elements_text(p_datos -> 'ods') AS x(valor);
  DELETE FROM solicitud_investigador_interes WHERE solicitud_id = p_id;
  INSERT INTO solicitud_investigador_interes (solicitud_id, interes)
    SELECT p_id, x.valor
      FROM jsonb_array_elements_text(p_datos -> 'intereses') AS x(valor);
  INSERT INTO solicitud_investigador_version
    (solicitud_id, numero_version, datos_snapshot, version_esquema)
  VALUES (p_id, v_solicitud.version_actual + 1, p_datos, '1');
END; $$;

COMMIT;

--------------------------------------------------------------------------------
-- Bloque F -- Entrega 5: borrado lógico, reportes y mantenimiento por procedimientos
--------------------------------------------------------------------------------
BEGIN;

-- F.1 Borrado lógico (investigador, patente, historico).
-- "Eliminar" no borra la fila: la marca como inactiva (activo = FALSE). El
-- trigger registra la fecha de baja y, al reactivar, limpia fecha y motivo.
CREATE OR REPLACE FUNCTION fn_registrar_baja() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.activo IS DISTINCT FROM OLD.activo THEN
    IF NEW.activo THEN
      NEW.fecha_baja := NULL;
      NEW.motivo_baja := NULL;
    ELSE
      NEW.fecha_baja := CURRENT_TIMESTAMP;
    END IF;
  END IF;
  RETURN NEW;
END; $$;

DROP TRIGGER IF EXISTS trg_investigador_baja ON investigador;
CREATE TRIGGER trg_investigador_baja
BEFORE UPDATE OF activo ON investigador
FOR EACH ROW EXECUTE FUNCTION fn_registrar_baja();

DROP TRIGGER IF EXISTS trg_patente_baja ON patente;
CREATE TRIGGER trg_patente_baja
BEFORE UPDATE OF activo ON patente
FOR EACH ROW EXECUTE FUNCTION fn_registrar_baja();

DROP TRIGGER IF EXISTS trg_historico_baja ON historico;
CREATE TRIGGER trg_historico_baja
BEFORE UPDATE OF activo ON historico
FOR EACH ROW EXECUTE FUNCTION fn_registrar_baja();

-- F.2 Procedimientos de baja y reactivación.
CREATE OR REPLACE PROCEDURE sp_eliminar_investigador(p_codigo_ucsm BIGINT, p_motivo VARCHAR DEFAULT NULL)
LANGUAGE plpgsql AS $$
BEGIN
  UPDATE investigador
     SET activo = FALSE, motivo_baja = NULLIF(btrim(p_motivo), '')
   WHERE codigo_ucsm = p_codigo_ucsm AND activo;          -- dispara trg_investigador_baja
  IF NOT FOUND THEN
    IF EXISTS (SELECT 1 FROM investigador WHERE codigo_ucsm = p_codigo_ucsm) THEN
      RAISE EXCEPTION 'El investigador % ya está dado de baja', p_codigo_ucsm;
    END IF;
    RAISE EXCEPTION 'No existe el investigador %', p_codigo_ucsm;
  END IF;
END; $$;

CREATE OR REPLACE PROCEDURE sp_reactivar_investigador(p_codigo_ucsm BIGINT)
LANGUAGE plpgsql AS $$
BEGIN
  UPDATE investigador SET activo = TRUE
   WHERE codigo_ucsm = p_codigo_ucsm AND NOT activo;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'El investigador % no existe o ya está activo', p_codigo_ucsm;
  END IF;
END; $$;

CREATE OR REPLACE PROCEDURE sp_eliminar_patente(p_n_patente VARCHAR, p_motivo VARCHAR DEFAULT NULL)
LANGUAGE plpgsql AS $$
BEGIN
  UPDATE patente
     SET activo = FALSE, motivo_baja = NULLIF(btrim(p_motivo), '')
   WHERE n_patente = p_n_patente AND activo;              -- dispara trg_patente_baja
  IF NOT FOUND THEN
    IF EXISTS (SELECT 1 FROM patente WHERE n_patente = p_n_patente) THEN
      RAISE EXCEPTION 'La patente % ya está dada de baja', p_n_patente;
    END IF;
    RAISE EXCEPTION 'No existe la patente %', p_n_patente;
  END IF;
END; $$;

CREATE OR REPLACE PROCEDURE sp_reactivar_patente(p_n_patente VARCHAR)
LANGUAGE plpgsql AS $$
BEGIN
  UPDATE patente SET activo = TRUE
   WHERE n_patente = p_n_patente AND NOT activo;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'La patente % no existe o ya está activa', p_n_patente;
  END IF;
END; $$;

CREATE OR REPLACE PROCEDURE sp_eliminar_historico(p_uuid UUID, p_motivo VARCHAR DEFAULT NULL)
LANGUAGE plpgsql AS $$
BEGIN
  UPDATE historico
     SET activo = FALSE, motivo_baja = NULLIF(btrim(p_motivo), '')
   WHERE uuid = p_uuid AND activo;                        -- dispara trg_historico_baja
  IF NOT FOUND THEN
    IF EXISTS (SELECT 1 FROM historico WHERE uuid = p_uuid) THEN
      RAISE EXCEPTION 'La publicación % ya está dada de baja', p_uuid;
    END IF;
    RAISE EXCEPTION 'No existe el registro historico %', p_uuid;
  END IF;
END; $$;

CREATE OR REPLACE PROCEDURE sp_reactivar_historico(p_uuid UUID)
LANGUAGE plpgsql AS $$
BEGIN
  UPDATE historico SET activo = TRUE
   WHERE uuid = p_uuid AND NOT activo;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'La publicación % no existe o ya está activa', p_uuid;
  END IF;
END; $$;

-- F.3 Reportes (consultas) como procedimientos.
-- Cada procedimiento abre un cursor con el resultado; el aplicativo hace
-- CALL sp_reporte_NN('reporte') y luego FETCH ALL FROM reporte en la misma
-- transacción. Solo consideran registros activos (borrado lógico).

-- 1. Total de investigadores
CREATE OR REPLACE PROCEDURE sp_reporte_01(INOUT p_resultado REFCURSOR DEFAULT 'reporte')
LANGUAGE plpgsql AS $$
BEGIN
  OPEN p_resultado FOR
    SELECT COUNT(*) AS total_investigadores_unicos
      FROM investigador
     WHERE activo;
END; $$;

-- 2. Escuelas profesionales con más investigadores
CREATE OR REPLACE PROCEDURE sp_reporte_02(INOUT p_resultado REFCURSOR DEFAULT 'reporte')
LANGUAGE plpgsql AS $$
BEGIN
  OPEN p_resultado FOR
    SELECT escuela_profesional, COUNT(*) AS total_miembros
      FROM investigador
     WHERE activo
     GROUP BY escuela_profesional
     ORDER BY total_miembros DESC, escuela_profesional;
END; $$;

-- 3. Directorio de investigadores con datos personales (JOIN)
CREATE OR REPLACE PROCEDURE sp_reporte_03(INOUT p_resultado REFCURSOR DEFAULT 'reporte')
LANGUAGE plpgsql AS $$
BEGIN
  OPEN p_resultado FOR
    SELECT i.codigo_ucsm,
           CONCAT(p.apellido_paterno, ' ', p.apellido_materno, ', ', p.nombres) AS nombre_completo,
           p.dni, p.genero, i.correo_elec, i.n_celular, i.escuela_profesional
      FROM investigador i
      JOIN persona p ON i.dni = p.dni
     WHERE i.activo
     ORDER BY nombre_completo;
END; $$;

-- 4. Investigadores sin patentes asociadas (JOIN)
CREATE OR REPLACE PROCEDURE sp_reporte_04(INOUT p_resultado REFCURSOR DEFAULT 'reporte')
LANGUAGE plpgsql AS $$
BEGIN
  OPEN p_resultado FOR
    SELECT i.codigo_ucsm, p.nombres, p.apellido_paterno, p.apellido_materno, i.escuela_profesional
      FROM investigador i
      JOIN persona p ON i.dni = p.dni
      LEFT JOIN formato_investigador fi ON i.codigo_ucsm = fi.codigo_ucsm
      LEFT JOIN formato_patente_investigador fpi ON fi.n_formato_inv = fpi.n_formato_inv
     WHERE i.activo AND fpi.n_formato_pat IS NULL
     ORDER BY p.apellido_paterno, p.apellido_materno;
END; $$;

-- 5. Evolución de publicaciones por año
CREATE OR REPLACE PROCEDURE sp_reporte_05(INOUT p_resultado REFCURSOR DEFAULT 'reporte')
LANGUAGE plpgsql AS $$
BEGIN
  OPEN p_resultado FOR
    SELECT publication_year, COUNT(*) AS total_publicaciones
      FROM historico
     WHERE activo
     GROUP BY publication_year
     ORDER BY publication_year;
END; $$;

-- 6. Producción por tipo de documento
CREATE OR REPLACE PROCEDURE sp_reporte_06(INOUT p_resultado REFCURSOR DEFAULT 'reporte')
LANGUAGE plpgsql AS $$
BEGIN
  OPEN p_resultado FOR
    SELECT type, COUNT(*) AS cantidad
      FROM historico
     WHERE activo
     GROUP BY type
     ORDER BY cantidad DESC, type;
END; $$;

-- 7. Publicaciones recientes por fecha de creación
CREATE OR REPLACE PROCEDURE sp_reporte_07(INOUT p_resultado REFCURSOR DEFAULT 'reporte')
LANGUAGE plpgsql AS $$
BEGIN
  OPEN p_resultado FOR
    SELECT uuid, title, publication_year, create_date, portal_url
      FROM historico
     WHERE activo AND create_date IS NOT NULL
     ORDER BY create_date DESC
     LIMIT 10;
END; $$;

-- 8. Publicaciones por idioma
CREATE OR REPLACE PROCEDURE sp_reporte_08(INOUT p_resultado REFCURSOR DEFAULT 'reporte')
LANGUAGE plpgsql AS $$
BEGIN
  OPEN p_resultado FOR
    SELECT language, COUNT(*) AS total
      FROM historico
     WHERE activo
     GROUP BY language
     ORDER BY total DESC, language;
END; $$;

-- 9. Reportes generados por coordinador (JOIN)
CREATE OR REPLACE PROCEDURE sp_reporte_09(INOUT p_resultado REFCURSOR DEFAULT 'reporte')
LANGUAGE plpgsql AS $$
BEGIN
  OPEN p_resultado FOR
    SELECT c.codigo_ucsm, p.nombres, p.apellido_paterno,
           COUNT(r.dia) AS total_reportes_emitidos
      FROM coordinador_repositorios c
      JOIN persona p ON c.dni = p.dni
      LEFT JOIN reporte r ON c.codigo_ucsm = r.codigo_ucsm_coordinador
     GROUP BY c.codigo_ucsm, p.nombres, p.apellido_paterno
     ORDER BY total_reportes_emitidos DESC, c.codigo_ucsm;
END; $$;

-- 10. Enlaces de cada publicación (JOIN)
CREATE OR REPLACE PROCEDURE sp_reporte_10(INOUT p_resultado REFCURSOR DEFAULT 'reporte')
LANGUAGE plpgsql AS $$
BEGIN
  OPEN p_resultado FOR
    SELECT h.title, l.link_type, l.url, l.description
      FROM historico h
      JOIN historico_links l ON h.uuid = l.uuid
     WHERE h.activo
     ORDER BY h.title;
END; $$;

-- 11. Investigadores asociados a cada ODS (JOIN)
CREATE OR REPLACE PROCEDURE sp_reporte_11(INOUT p_resultado REFCURSOR DEFAULT 'reporte')
LANGUAGE plpgsql AS $$
BEGIN
  OPEN p_resultado FOR
    SELECT o.ods, COUNT(*) AS total_asociaciones
      FROM formato_inv_ods o
      JOIN formato_investigador fi ON fi.n_formato_inv = o.n_formato_inv
      JOIN investigador i ON i.codigo_ucsm = fi.codigo_ucsm
     WHERE i.activo
     GROUP BY o.ods
     ORDER BY total_asociaciones DESC, o.ods;
END; $$;

-- 12. Patentes por país de registro y entidad
CREATE OR REPLACE PROCEDURE sp_reporte_12(INOUT p_resultado REFCURSOR DEFAULT 'reporte')
LANGUAGE plpgsql AS $$
BEGIN
  OPEN p_resultado FOR
    SELECT pais, editorial, COUNT(*) AS total_patentes
      FROM patente
     WHERE activo
     GROUP BY pais, editorial
     ORDER BY total_patentes DESC, pais;
END; $$;

-- 13. Investigadores con sus ODS vinculados (JOIN)
CREATE OR REPLACE PROCEDURE sp_reporte_13(INOUT p_resultado REFCURSOR DEFAULT 'reporte')
LANGUAGE plpgsql AS $$
BEGIN
  OPEN p_resultado FOR
    SELECT i.codigo_ucsm,
           p.apellido_paterno || ' ' || p.apellido_materno || ', ' || p.nombres AS investigador,
           i.escuela_profesional,
           string_agg(o.ods, ' | ' ORDER BY o.ods) AS ods_vinculados
      FROM investigador i
      JOIN persona p ON p.dni = i.dni
      JOIN formato_investigador fi ON fi.codigo_ucsm = i.codigo_ucsm
      JOIN formato_inv_ods o ON o.n_formato_inv = fi.n_formato_inv
     WHERE i.activo
     GROUP BY i.codigo_ucsm, p.apellido_paterno, p.apellido_materno, p.nombres, i.escuela_profesional
     ORDER BY investigador;
END; $$;

-- 14. Patentes con sus inventores registrados (JOIN)
CREATE OR REPLACE PROCEDURE sp_reporte_14(INOUT p_resultado REFCURSOR DEFAULT 'reporte')
LANGUAGE plpgsql AS $$
BEGIN
  OPEN p_resultado FOR
    SELECT pa.n_patente, pa.titulo_patente, pa.pais,
           p.apellido_paterno || ' ' || p.apellido_materno || ', ' || p.nombres AS inventor,
           i.escuela_profesional
      FROM patente pa
      JOIN formato_patente fp ON fp.n_patente = pa.n_patente
      JOIN formato_patente_investigador fpi ON fpi.n_formato_pat = fp.n_formato_pat
      JOIN formato_investigador fi ON fi.n_formato_inv = fpi.n_formato_inv
      JOIN investigador i ON i.codigo_ucsm = fi.codigo_ucsm
      JOIN persona p ON p.dni = i.dni
     WHERE pa.activo
     ORDER BY pa.fecha_registro DESC, pa.n_patente, inventor;
END; $$;

-- 15. Formatos de investigador y coordinador que los valida (JOIN)
CREATE OR REPLACE PROCEDURE sp_reporte_15(INOUT p_resultado REFCURSOR DEFAULT 'reporte')
LANGUAGE plpgsql AS $$
BEGIN
  OPEN p_resultado FOR
    SELECT fi.n_formato_inv,
           pinv.apellido_paterno || ' ' || pinv.apellido_materno || ', ' || pinv.nombres AS investigador,
           pcoo.apellido_paterno || ' ' || pcoo.apellido_materno || ', ' || pcoo.nombres AS coordinador_validador,
           c.funcion
      FROM formato_investigador fi
      JOIN investigador i ON i.codigo_ucsm = fi.codigo_ucsm
      JOIN persona pinv ON pinv.dni = i.dni
      JOIN coordinador_repositorios c ON c.codigo_ucsm = fi.codigo_ucsm_coordinador
      JOIN persona pcoo ON pcoo.dni = c.dni
     WHERE i.activo
     ORDER BY coordinador_validador, investigador;
END; $$;

-- F.4 Mantenimiento del administrador por procedimientos (CRUD genérico).
-- El aplicativo valida los nombres de columnas contra el catálogo; aquí además
-- se valida la tabla y todo identificador se escapa con format('%I').
-- Las tablas con borrado lógico (columnas activo y fecha_baja) se dan de baja
-- en lugar de borrarse.
CREATE OR REPLACE FUNCTION fn_admin_validar_tabla(p_tabla TEXT) RETURNS VOID
LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                  WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                    AND table_name = p_tabla) THEN
    RAISE EXCEPTION 'No existe la tabla %', p_tabla;
  END IF;
END; $$;

CREATE OR REPLACE FUNCTION fn_admin_condicion_clave(p_clave JSONB) RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$
  SELECT string_agg(format('t.%1$I IS NOT DISTINCT FROM c.%1$I', k), ' AND ')
    FROM jsonb_object_keys(p_clave) AS k
$$;

CREATE OR REPLACE PROCEDURE sp_admin_insertar(
  p_tabla TEXT, p_valores JSONB, INOUT p_fila JSONB DEFAULT NULL)
LANGUAGE plpgsql AS $$
DECLARE
  v_columnas TEXT;
BEGIN
  PERFORM fn_admin_validar_tabla(p_tabla);
  SELECT string_agg(format('%I', k), ', ') INTO v_columnas
    FROM jsonb_object_keys(COALESCE(p_valores, '{}'::jsonb)) AS k;
  IF v_columnas IS NULL THEN
    EXECUTE format('INSERT INTO %1$I AS t DEFAULT VALUES RETURNING to_jsonb(t.*)', p_tabla)
       INTO p_fila;
  ELSE
    EXECUTE format('INSERT INTO %1$I AS t (%2$s) SELECT %2$s FROM jsonb_populate_record(NULL::%1$I, $1) '
                   'RETURNING to_jsonb(t.*)', p_tabla, v_columnas)
       INTO p_fila USING p_valores;
  END IF;
END; $$;

CREATE OR REPLACE PROCEDURE sp_admin_actualizar(
  p_tabla TEXT, p_clave JSONB, p_valores JSONB, INOUT p_fila JSONB DEFAULT NULL)
LANGUAGE plpgsql AS $$
DECLARE
  v_set TEXT;
BEGIN
  PERFORM fn_admin_validar_tabla(p_tabla);
  IF p_clave IS NULL OR p_clave = '{}'::jsonb THEN
    RAISE EXCEPTION 'Indique la clave primaria de la fila.';
  END IF;
  SELECT string_agg(format('%1$I = r.%1$I', k), ', ') INTO v_set
    FROM jsonb_object_keys(COALESCE(p_valores, '{}'::jsonb)) AS k;
  IF v_set IS NULL THEN
    RAISE EXCEPTION 'No hay cambios para guardar.';
  END IF;
  EXECUTE format('UPDATE %1$I AS t SET %2$s '
                 'FROM jsonb_populate_record(NULL::%1$I, $1) AS r, '
                 '     jsonb_populate_record(NULL::%1$I, $2) AS c '
                 'WHERE %3$s RETURNING to_jsonb(t.*)',
                 p_tabla, v_set, fn_admin_condicion_clave(p_clave))
     INTO p_fila USING p_valores, p_clave;
  IF p_fila IS NULL THEN
    RAISE EXCEPTION 'La fila ya no existe; recargue la tabla.' USING ERRCODE = 'no_data_found';
  END IF;
END; $$;

CREATE OR REPLACE PROCEDURE sp_admin_eliminar(
  p_tabla TEXT, p_clave JSONB, INOUT p_filas INTEGER DEFAULT 0)
LANGUAGE plpgsql AS $$
BEGIN
  PERFORM fn_admin_validar_tabla(p_tabla);
  IF p_clave IS NULL OR p_clave = '{}'::jsonb THEN
    RAISE EXCEPTION 'Indique la clave primaria de la fila.';
  END IF;
  IF (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = 'public' AND table_name = p_tabla
         AND column_name IN ('activo', 'fecha_baja')) = 2 THEN
    -- Borrado lógico: dispara el trigger trg_*_baja.
    EXECUTE format('UPDATE %1$I AS t SET activo = FALSE '
                   'FROM jsonb_populate_record(NULL::%1$I, $1) AS c WHERE %2$s AND t.activo',
                   p_tabla, fn_admin_condicion_clave(p_clave)) USING p_clave;
  ELSE
    EXECUTE format('DELETE FROM %1$I AS t USING jsonb_populate_record(NULL::%1$I, $1) AS c WHERE %2$s',
                   p_tabla, fn_admin_condicion_clave(p_clave)) USING p_clave;
  END IF;
  GET DIAGNOSTICS p_filas = ROW_COUNT;
  IF p_filas = 0 THEN
    RAISE EXCEPTION 'La fila ya no existe o ya está dada de baja; recargue la tabla.'
      USING ERRCODE = 'no_data_found';
  END IF;
END; $$;

COMMIT;
