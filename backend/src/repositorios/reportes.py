"""Reportes: las 15 consultas (procedimientos sp_reporte_NN) y sp_generar_reporte."""
from ..db.conexion import consultar_dicts, ejecutar_procedimiento, ejecutar_reporte
from . import utilidades as u
from .catalogo_reportes import CONSULTAS

# (titulo de seccion, tabla, columna) de las 8 tablas que llena sp_generar_reporte
SECCIONES = [
    ("Total de publicaciones", "total_publicaciones", "publicacion"),
    ("Total de investigadores", "total_investigadores", "investigador"),
    ("Escuelas profesionales", "cantidad_escuelas_prof", "escuelas_prof"),
    ("ODS vinculados", "cantidad_ods_vinculados", "ods_vinc"),
    ("Investigador destacado por escuela", "top_escu_invest", "top_escu_invest"),
    ("Ranking de ODS", "rankings_ods", "ranking_ods"),
    ("Distribución de ODS", "distribuciones_ods", "distribucion_ods"),
    ("Top de escuelas", "tops_escuelas", "top_escuelas"),
]


_SQL_INDICADORES = """
SELECT (SELECT COUNT(*) FROM investigador WHERE activo)                         AS investigadores,
       (SELECT COUNT(DISTINCT escuela_profesional) FROM investigador WHERE activo) AS escuelas,
       (SELECT COUNT(*) FROM historico WHERE activo)                            AS publicaciones,
       (SELECT COUNT(*) FROM patente WHERE activo)                              AS patentes,
       (SELECT COUNT(DISTINCT substring(o.ods FROM '^ODS ([0-9]+):'))
          FROM formato_inv_ods o
          JOIN formato_investigador fi ON fi.n_formato_inv = o.n_formato_inv
          JOIN investigador i ON i.codigo_ucsm = fi.codigo_ucsm
         WHERE i.activo)                                                         AS ods_vinculados
"""

_SQL_RANKING_ODS = """
SELECT MIN(o.ods) AS ods, COUNT(*) AS total
FROM formato_inv_ods o
JOIN formato_investigador fi ON fi.n_formato_inv = o.n_formato_inv
JOIN investigador i ON i.codigo_ucsm = fi.codigo_ucsm
WHERE i.activo
GROUP BY substring(o.ods FROM '^ODS [0-9]+')
ORDER BY total DESC, MIN(o.ods)
LIMIT 5
"""

_SQL_TOP_ESCUELAS = """
SELECT escuela_profesional AS escuela, COUNT(*) AS total
FROM investigador
WHERE activo
GROUP BY escuela_profesional
ORDER BY total DESC, escuela_profesional
LIMIT 3
"""


def indicadores():
    """Indicadores del Dashboard (Reporte) calculados al momento, para la pagina de inicio:
    totales, ranking de ODS (top 5) y escuelas con mas investigadores (top 3)."""
    datos = consultar_dicts(_SQL_INDICADORES)[0]
    datos["ranking_ods"] = [(f["ods"], f["total"]) for f in consultar_dicts(_SQL_RANKING_ODS)]
    datos["top_escuelas"] = [(f["escuela"], f["total"]) for f in consultar_dicts(_SQL_TOP_ESCUELAS)]
    return datos


def catalogo():
    """Lista de (id, titulo, usa_join)."""
    return [(c["id"], c["titulo"], c["usa_join"]) for c in CONSULTAS]


def ejecutar(id_consulta):
    """Ejecuta el procedimiento del reporte y devuelve (titulo, columnas, filas)."""
    for c in CONSULTAS:
        if c["id"] == id_consulta:
            columnas, filas = ejecutar_reporte(c["procedimiento"])
            return c["titulo"], columnas, filas
    raise u.ErrorOperacion(f"No existe la consulta {id_consulta}.")


def generar(fecha, coordinador):
    ejecutar_procedimiento("sp_generar_reporte",
                           [u.fecha(fecha, "La fecha del reporte"), coordinador], ["date", None])


def emitidos():
    """Filas (fecha AAAA-MM-DD, coordinador) de los reportes ya generados."""
    filas = consultar_dicts("""
        SELECT r.anio, r.mes, r.dia,
               p.apellido_paterno || ' ' || p.apellido_materno || ', ' || p.nombres AS coordinador
        FROM reporte r
        JOIN coordinador_repositorios c ON c.codigo_ucsm = r.codigo_ucsm_coordinador
        JOIN persona p ON p.dni = c.dni
        ORDER BY r.anio DESC, r.mes DESC, r.dia DESC""")
    return [(f"{f['anio']:04d}-{f['mes']:02d}-{f['dia']:02d}", f["coordinador"]) for f in filas]


def detalle(fecha):
    """Texto con lo que guardo sp_generar_reporte para esa fecha."""
    d = u.fecha(fecha, "La fecha del reporte")
    lineas = [f"REPORTE DEL {d.isoformat()}", ""]
    for titulo, tabla, columna in SECCIONES:
        filas = consultar_dicts(
            f"SELECT {columna} AS valor FROM {tabla} WHERE dia = %s AND mes = %s AND anio = %s "
            f"ORDER BY 1", (d.day, d.month, d.year))
        lineas.append(f"{titulo} ({len(filas)})")
        lineas.extend(f"   - {f['valor']}" for f in filas)
        lineas.append("")
    return "\n".join(lineas)
