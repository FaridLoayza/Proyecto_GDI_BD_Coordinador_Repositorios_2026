"""Reportes: las 15 consultas (procedimientos sp_reporte_NN) y sp_generar_reporte."""
from ..db.conexion import consultar_procedimiento, ejecutar_procedimiento, ejecutar_reporte
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


def indicadores():
    """Indicadores del Dashboard (Reporte) calculados al momento, para la pagina de inicio:
    totales, ranking de ODS (top 5) y escuelas con mas investigadores (top 3)."""
    datos = consultar_procedimiento("sp_indicadores_inicio")[0]
    datos["ranking_ods"] = [(f["ods"], f["total"])
                            for f in consultar_procedimiento("sp_ranking_ods_inicio")]
    datos["top_escuelas"] = [(f["escuela"], f["total"])
                             for f in consultar_procedimiento("sp_top_escuelas_inicio")]
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
    filas = consultar_procedimiento("sp_listar_reportes_emitidos")
    return [(f"{f['anio']:04d}-{f['mes']:02d}-{f['dia']:02d}", f["coordinador"]) for f in filas]


def detalle(fecha):
    """Texto con lo que guardo sp_generar_reporte para esa fecha."""
    d = u.fecha(fecha, "La fecha del reporte")
    lineas = [f"REPORTE DEL {d.isoformat()}", ""]
    valores = consultar_procedimiento("sp_detalle_reporte", [d], ["date"])
    for titulo, tabla, _columna in SECCIONES:
        filas = [f["valor"] for f in valores if f["seccion"] == tabla]
        lineas.append(f"{titulo} ({len(filas)})")
        lineas.extend(f"   - {valor}" for valor in filas)
        lineas.append("")
    return "\n".join(lineas)
