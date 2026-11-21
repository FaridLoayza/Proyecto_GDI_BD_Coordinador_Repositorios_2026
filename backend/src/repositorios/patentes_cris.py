"""Acceso a solicitudes de patente del portal CRIS."""
from ..db.conexion import consultar_dicts, ejecutar_procedimiento


_BASE = """
SELECT s.id, s.solicitante_codigo_ucsm, s.estado, s.n_patente,
       s.titulo_patente, s.editorial, s.fecha_registro, s.cip, s.pais,
       s.version_actual, s.creada_en,
       p.nombres, p.apellido_paterno, p.apellido_materno,
       COALESCE((
           SELECT array_agg(x.codigo_ucsm ORDER BY x.codigo_ucsm)
             FROM solicitud_patente_investigador x
            WHERE x.solicitud_patente_id = s.id
       ), '{}') AS inventores,
       COALESCE((
           SELECT jsonb_agg(jsonb_build_object(
               'campo', o.campo_ocde, 'objetivo', o.objetivo_ocde
           ) ORDER BY o.campo_ocde)
             FROM solicitud_patente_ocde o
            WHERE o.solicitud_patente_id = s.id
       ), '[]'::jsonb) AS clasificacion_ocde
  FROM solicitud_patente s
  JOIN investigador i ON i.codigo_ucsm = s.solicitante_codigo_ucsm
  JOIN persona p ON p.dni = i.dni
"""


def _normalizar(fila):
    fila["clasificacion_ocde"] = fila["clasificacion_ocde"] or []
    fila["revisiones"] = consultar_dicts("""
        SELECT version_evaluada, resultado, datos_evaluados, motivo,
               resuelto_por, resuelto_en
          FROM revision_solicitud_patente
         WHERE solicitud_patente_id = %s
         ORDER BY version_evaluada
    """, (fila["id"],))
    return fila


def listar():
    return [_normalizar(fila) for fila in consultar_dicts(
        _BASE + """
         WHERE s.estado IN ('pendiente_revision', 'observada')
         ORDER BY CASE s.estado WHEN 'pendiente_revision' THEN 0 ELSE 1 END,
                  s.creada_en, s.id
        """)]


def listar_de_investigador(codigo_ucsm):
    return [_normalizar(fila) for fila in consultar_dicts(
        _BASE + " WHERE s.solicitante_codigo_ucsm = %s ORDER BY s.creada_en DESC",
        (int(codigo_ucsm),))]


def obtener(solicitud_id):
    filas = consultar_dicts(_BASE + " WHERE s.id = %s", (int(solicitud_id),))
    return _normalizar(filas[0]) if filas else None


def crear(solicitante, datos):
    ejecutar_procedimiento(
        "sp_crear_solicitud_patente",
        [
            int(solicitante), datos["n_patente"], datos["titulo"],
            datos["editorial"], datos["fecha_registro"], datos["cip"],
            datos["pais"], datos["inventores"], datos["campos_ocde"],
            datos["objetivos_ocde"],
        ],
        [None] * 7 + ["bigint[]", "varchar[]", "varchar[]"],
    )


def actualizar(solicitud_id, datos):
    ejecutar_procedimiento(
        "sp_actualizar_solicitud_patente",
        [
            int(solicitud_id), datos["n_patente"], datos["titulo"],
            datos["editorial"], datos["fecha_registro"], datos["cip"],
            datos["pais"], datos["inventores"], datos["campos_ocde"],
            datos["objetivos_ocde"],
        ],
        [None] * 7 + ["bigint[]", "varchar[]", "varchar[]"],
    )


def resolver(solicitud_id, coordinador, resultado, motivo=None):
    ejecutar_procedimiento(
        "sp_resolver_solicitud_patente",
        [int(solicitud_id), int(coordinador), resultado, motivo],
    )
