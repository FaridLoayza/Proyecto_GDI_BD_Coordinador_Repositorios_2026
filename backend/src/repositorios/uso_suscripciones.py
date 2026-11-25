"""Tarea 2: uso de suscripciones de biblioteca (COUNTER) y resumen del repositorio.

- importar(): guarda un reporte COUNTER ya leído en uso_suscripcion y deja la
  carga registrada en integracion_ejecucion (sistema 'counter' o 'sushi').
  Reimportar el mismo mes actualiza el valor; no duplica filas.
- Consultas para la pestaña "Uso de suscripciones" y el "Resumen" del Histórico.
"""
from psycopg2.extras import Json

from ..db.conexion import ErrorOperacion, consultar_procedimiento


def importar(registros, archivo, coordinador, proveedor=None, sistema="counter", disparador="manual"):
    """Guarda los registros en una sola transacción (sp_importar_uso_suscripcion).
    Devuelve los contadores."""
    if not registros:
        raise ErrorOperacion("No hay registros de uso para importar.")
    datos = [{"plataforma": r["plataforma"], "periodo": str(r["periodo"]),
              "metrica": r["metrica"], "valor": r["valor"]} for r in registros]
    return consultar_procedimiento(
        "sp_importar_uso_suscripcion",
        [sistema, disparador, coordinador, (archivo or "")[:255] or None,
         (proveedor or "Elsevier")[:80], Json(datos)],
        [None, None, "bigint", "varchar", None, "jsonb"])[0]


def opciones():
    """Plataformas, métricas y rango de meses disponibles (para los filtros)."""
    filas = consultar_procedimiento("sp_opciones_uso")[0]
    return {
        "plataformas": filas["plataformas"] or [],
        "metricas": filas["metricas"] or [],
        "desde": filas["desde"].isoformat() if filas["desde"] else None,
        "hasta": filas["hasta"].isoformat() if filas["hasta"] else None,
    }


def _consultar(metrica, plataformas, desde, hasta):
    return consultar_procedimiento(
        "sp_consultar_uso", [metrica, list(plataformas) if plataformas else None, desde, hasta],
        ["varchar", "varchar[]", "date", "date"])


def serie(metrica="Total_Item_Requests", plataformas=None, desde=None, hasta=None):
    """Valores por plataforma y mes de una métrica, más el total por plataforma."""
    filas = [{"plataforma": f["plataforma"], "periodo": f["periodo"], "valor": f["valor"]}
             for f in _consultar(metrica, plataformas, desde, hasta)]
    totales = {}
    for fila in filas:
        totales[fila["plataforma"]] = totales.get(fila["plataforma"], 0) + fila["valor"]
    return {
        "metrica": metrica,
        "periodos": sorted({f["periodo"] for f in filas}),
        "filas": filas,
        "totales": [{"plataforma": p, "total": t} for p, t in sorted(totales.items(), key=lambda x: -x[1])],
    }


def tabla_exportable(plataformas=None, desde=None, hasta=None):
    """Todas las métricas filtradas, una fila por plataforma, mes y métrica (para CSV)."""
    return _consultar(None, plataformas, desde, hasta)


def importaciones(limite=10):
    return consultar_procedimiento("sp_listar_importaciones_uso", [limite])


def resumen_repositorio():
    """Indicadores del Histórico (contenido del repositorio) y del uso del último año."""
    def seccion(nombre):
        return consultar_procedimiento("sp_resumen_repositorio", [nombre])

    totales = seccion("totales")[0]
    por_anio = seccion("por_anio")
    por_tipo = seccion("por_tipo")
    por_escuela = seccion("por_escuela")
    por_ods = seccion("por_ods")
    uso = seccion("uso_12_meses")
    ultimo_mes = seccion("ultimo_mes")[0]["mes"]
    return {
        "publicaciones": totales["publicaciones"],
        "tipos": totales["tipos"],
        "ultima_sincronizacion": totales["ultima_sincronizacion"],
        "por_anio": por_anio,
        "por_tipo": por_tipo,
        "por_escuela": por_escuela,
        "por_ods": por_ods,
        "uso_ultimos_12_meses": uso,
        "uso_total_ultimos_12_meses": sum(f["total"] for f in uso),
        "uso_ultimo_mes": ultimo_mes,
    }
