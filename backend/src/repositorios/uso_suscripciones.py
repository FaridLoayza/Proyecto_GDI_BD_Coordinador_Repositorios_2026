"""Tarea 2: uso de suscripciones de biblioteca (COUNTER) y resumen del repositorio.

- importar(): guarda un reporte COUNTER ya leído en uso_suscripcion y deja la
  carga registrada en integracion_ejecucion (sistema 'counter' o 'sushi').
  Reimportar el mismo mes actualiza el valor; no duplica filas.
- Consultas para la pestaña "Uso de suscripciones" y el "Resumen" del Histórico.
"""
import psycopg2

from ..db.conexion import ErrorOperacion, _mensaje_operacion, conectar, consultar_dicts

_SQL_EJECUCION = """
INSERT INTO integracion_ejecucion
  (sistema, operacion, disparador, estado, iniciada_en, finalizada_en,
   registros_leidos, codigo_ucsm_coordinador, archivo)
VALUES (%s, 'importar_uso_counter', %s, 'iniciada', CURRENT_TIMESTAMP, NULL, %s, %s, %s)
RETURNING id
"""

_SQL_UPSERT = """
INSERT INTO uso_suscripcion (plataforma, proveedor, periodo, metrica, valor, ejecucion_id)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (plataforma, periodo, metrica) DO UPDATE
   SET valor = EXCLUDED.valor,
       proveedor = EXCLUDED.proveedor,
       ejecucion_id = EXCLUDED.ejecucion_id,
       actualizado_en = CURRENT_TIMESTAMP
RETURNING (xmax = 0) AS creado
"""


def importar(registros, archivo, coordinador, proveedor=None, sistema="counter", disparador="manual"):
    """Guarda los registros en una sola transacción. Devuelve los contadores."""
    if not registros:
        raise ErrorOperacion("No hay registros de uso para importar.")
    proveedor = (proveedor or "Elsevier")[:80]
    conn = conectar()
    try:
        with conn.cursor() as cur:
            cur.execute(_SQL_EJECUCION, (sistema, disparador, len(registros), coordinador, (archivo or "")[:255] or None))
            ejecucion_id = cur.fetchone()[0]
            creados = actualizados = 0
            for r in registros:
                cur.execute(_SQL_UPSERT, (r["plataforma"], proveedor, r["periodo"], r["metrica"], r["valor"], ejecucion_id))
                if cur.fetchone()[0]:
                    creados += 1
                else:
                    actualizados += 1
            cur.execute("""
                UPDATE integracion_ejecucion
                   SET estado = 'completada', finalizada_en = CURRENT_TIMESTAMP,
                       registros_creados = %s, registros_actualizados = %s
                 WHERE id = %s
            """, (creados, actualizados, ejecucion_id))
        conn.commit()
        return {"ejecucion_id": ejecucion_id, "creados": creados, "actualizados": actualizados}
    except psycopg2.Error as exc:
        conn.rollback()
        raise ErrorOperacion(_mensaje_operacion(exc)) from exc
    finally:
        conn.close()


def opciones():
    """Plataformas, métricas y rango de meses disponibles (para los filtros)."""
    filas = consultar_dicts("""
        SELECT array_agg(DISTINCT plataforma ORDER BY plataforma) AS plataformas,
               array_agg(DISTINCT metrica ORDER BY metrica) AS metricas,
               min(periodo) AS desde, max(periodo) AS hasta
          FROM uso_suscripcion
    """)[0]
    return {
        "plataformas": filas["plataformas"] or [],
        "metricas": filas["metricas"] or [],
        "desde": filas["desde"].isoformat() if filas["desde"] else None,
        "hasta": filas["hasta"].isoformat() if filas["hasta"] else None,
    }


def _filtros(plataformas, desde, hasta, metrica):
    condiciones, parametros = ["TRUE"], []
    if metrica:
        condiciones.append("metrica = %s")
        parametros.append(metrica)
    if plataformas:
        condiciones.append("plataforma = ANY(%s)")
        parametros.append(list(plataformas))
    if desde:
        condiciones.append("periodo >= %s")
        parametros.append(desde)
    if hasta:
        condiciones.append("periodo <= %s")
        parametros.append(hasta)
    return " AND ".join(condiciones), parametros


def serie(metrica="Total_Item_Requests", plataformas=None, desde=None, hasta=None):
    """Valores por plataforma y mes de una métrica, más el total por plataforma."""
    donde, parametros = _filtros(plataformas, desde, hasta, metrica)
    filas = consultar_dicts(f"""
        SELECT plataforma, to_char(periodo, 'YYYY-MM') AS periodo, valor
          FROM uso_suscripcion
         WHERE {donde}
         ORDER BY periodo, plataforma
    """, tuple(parametros))
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
    donde, parametros = _filtros(plataformas, desde, hasta, None)
    return consultar_dicts(f"""
        SELECT plataforma, proveedor, to_char(periodo, 'YYYY-MM') AS periodo, metrica, valor
          FROM uso_suscripcion
         WHERE {donde}
         ORDER BY periodo, plataforma, metrica
    """, tuple(parametros))


def importaciones(limite=10):
    return consultar_dicts("""
        SELECT e.id, e.sistema, e.archivo, e.estado, e.iniciada_en, e.registros_leidos,
               e.registros_creados, e.registros_actualizados, e.codigo_ucsm_coordinador
          FROM integracion_ejecucion e
         WHERE e.sistema IN ('counter', 'sushi')
         ORDER BY e.iniciada_en DESC, e.id DESC
         LIMIT %s
    """, (limite,))


def resumen_repositorio():
    """Indicadores del Histórico (contenido del repositorio) y del uso del último año."""
    totales = consultar_dicts("""
        SELECT COUNT(*) AS publicaciones,
               max(synced_at) AS ultima_sincronizacion,
               COUNT(DISTINCT type) AS tipos
          FROM historico WHERE activo
    """)[0]
    por_anio = consultar_dicts("""
        SELECT publication_year AS anio, COUNT(*) AS total
          FROM historico WHERE activo
         GROUP BY publication_year ORDER BY publication_year DESC LIMIT 8
    """)
    por_tipo = consultar_dicts("""
        SELECT type AS tipo, COUNT(*) AS total
          FROM historico WHERE activo
         GROUP BY type ORDER BY total DESC, type LIMIT 8
    """)
    por_escuela = consultar_dicts("""
        SELECT i.escuela_profesional AS escuela, COUNT(DISTINCT ih.uuid) AS total
          FROM investigador_historico ih
          JOIN investigador i ON i.codigo_ucsm = ih.codigo_ucsm
          JOIN historico h ON h.uuid = ih.uuid AND h.activo
         GROUP BY i.escuela_profesional ORDER BY total DESC, escuela LIMIT 8
    """)
    por_ods = consultar_dicts("""
        SELECT o.ods, COUNT(DISTINCT ih.uuid) AS total
          FROM investigador_historico ih
          JOIN formato_investigador f ON f.codigo_ucsm = ih.codigo_ucsm
          JOIN formato_inv_ods o ON o.n_formato_inv = f.n_formato_inv
          JOIN historico h ON h.uuid = ih.uuid AND h.activo
         GROUP BY o.ods ORDER BY total DESC, o.ods LIMIT 8
    """)
    uso = consultar_dicts("""
        WITH ultimo AS (SELECT max(periodo) AS fin FROM uso_suscripcion)
        SELECT u.plataforma, SUM(u.valor) AS total
          FROM uso_suscripcion u, ultimo
         WHERE u.metrica = 'Total_Item_Requests'
           AND u.periodo > ultimo.fin - INTERVAL '12 months'
         GROUP BY u.plataforma ORDER BY total DESC
    """)
    ultimo_mes = consultar_dicts("SELECT to_char(max(periodo), 'YYYY-MM') AS mes FROM uso_suscripcion")[0]["mes"]
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
