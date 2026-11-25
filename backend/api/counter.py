"""Lectura de reportes COUNTER 5 de uso de suscripciones (Tarea 2).

COUNTER (Project COUNTER, release 5) es el estándar con el que los editores
(Elsevier: ScienceDirect, Scopus, Engineering Village…) informan el uso de
las suscripciones de una institución. El reporte se descarga del portal de
administración del editor o por la API SUSHI y se importa aquí.

Formatos aceptados (Platform Report "PR" o Title Report "TR"):
- JSON COUNTER 5.0: Report_Items[].Performance[].Instance[] (Metric_Type, Count).
- JSON COUNTER 5.1: Report_Items[].Attribute_Performance[].Performance{métrica: {"AAAA-MM": n}}.
- CSV/TSV tabular: cabecera COUNTER, fila de columnas con "Platform" y
  "Metric_Type", y una columna por mes ("Jan-2025" o "2025-01").

Los valores se agregan por plataforma, mes y métrica: nunca hay datos por
estudiante (COUNTER no los entrega).
"""
import csv
import datetime
import io
import json
import re

MAX_BYTES = 10 * 1024 * 1024
METRICAS = (
    "Total_Item_Investigations", "Unique_Item_Investigations",
    "Total_Item_Requests", "Unique_Item_Requests",
    "Unique_Title_Investigations", "Unique_Title_Requests",
    "Searches_Platform", "Searches_Automated", "Searches_Federated",
    "Searches_Regular", "No_License", "Limit_Exceeded",
)
_MESES = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def _periodo(texto):
    """'2025-03', '2025-03-01', 'Mar-2025' o 'Mar 2025' -> date(2025, 3, 1); None si no es un mes."""
    texto = str(texto or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})(?:-\d{2})?", texto)
    if m:
        anio, mes = int(m.group(1)), int(m.group(2))
    else:
        m = re.fullmatch(r"([A-Za-z]{3})[- ](\d{4})", texto)
        if not m or m.group(1).lower() not in _MESES:
            return None
        anio, mes = int(m.group(2)), _MESES[m.group(1).lower()]
    if not 1 <= mes <= 12 or anio < 2000:
        return None
    return datetime.date(anio, mes, 1)


def _entero(valor):
    try:
        numero = int(str(valor).replace(",", "").strip() or 0)
    except ValueError:
        return None
    return numero if numero >= 0 else None


class _Acumulador:
    def __init__(self):
        self.valores = {}
        self.ignoradas = set()
        self.proveedor = None

    def sumar(self, plataforma, periodo, metrica, valor):
        plataforma = str(plataforma or "").strip()
        if not plataforma or periodo is None or valor is None:
            return
        if metrica not in METRICAS:
            self.ignoradas.add(str(metrica))
            return
        clave = (plataforma[:80], periodo, metrica)
        self.valores[clave] = self.valores.get(clave, 0) + valor


def _leer_json(datos, acc):
    if not isinstance(datos, dict) or "Report_Items" not in datos:
        raise ValueError("El JSON no tiene el formato COUNTER 5 (falta Report_Items).")
    cabecera = datos.get("Report_Header") or {}
    acc.proveedor = (cabecera.get("Created_By") or "").strip() or None
    for item in datos.get("Report_Items") or []:
        plataforma = item.get("Platform") or item.get("Publisher") or acc.proveedor
        # COUNTER 5.0
        for perf in item.get("Performance") or []:
            if not isinstance(perf, dict):
                continue
            periodo = _periodo((perf.get("Period") or {}).get("Begin_Date"))
            for inst in perf.get("Instance") or []:
                acc.sumar(plataforma, periodo, inst.get("Metric_Type"), _entero(inst.get("Count")))
        # COUNTER 5.1
        for attr in item.get("Attribute_Performance") or []:
            for metrica, meses in (attr.get("Performance") or {}).items():
                for mes, cuenta in (meses or {}).items():
                    acc.sumar(plataforma, _periodo(mes), metrica, _entero(cuenta))


def _leer_tabular(texto, acc):
    muestra = texto[:4096]
    delimitador = "\t" if muestra.count("\t") > muestra.count(",") else ","
    filas = list(csv.reader(io.StringIO(texto), delimiter=delimitador))
    cabecera = None
    for i, fila in enumerate(filas):
        nombres = [c.strip() for c in fila]
        if "Platform" in nombres and "Metric_Type" in nombres:
            cabecera = i
            break
        if nombres and nombres[0] == "Created_By" and len(nombres) > 1:
            acc.proveedor = nombres[1].strip() or None
    if cabecera is None:
        raise ValueError("El archivo no tiene las columnas COUNTER 'Platform' y 'Metric_Type'.")
    columnas = [c.strip() for c in filas[cabecera]]
    i_plat, i_met = columnas.index("Platform"), columnas.index("Metric_Type")
    meses = [(j, _periodo(c)) for j, c in enumerate(columnas) if _periodo(c)]
    if not meses:
        raise ValueError("El archivo no tiene columnas de meses (por ejemplo 'Jan-2025').")
    for fila in filas[cabecera + 1:]:
        if len(fila) <= max(i_plat, i_met):
            continue
        for j, periodo in meses:
            if j < len(fila):
                acc.sumar(fila[i_plat], periodo, fila[i_met].strip(), _entero(fila[j]))


def parse_counter(contenido, nombre_archivo=""):
    """Devuelve (registros, resumen). Lanza ValueError con un mensaje para el usuario."""
    if not contenido:
        raise ValueError("El archivo está vacío.")
    if len(contenido) > MAX_BYTES:
        raise ValueError("El archivo supera los 10 MB.")
    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = contenido.decode("latin-1")
    acc = _Acumulador()
    if nombre_archivo.lower().endswith(".json") or texto.lstrip().startswith("{"):
        try:
            datos = json.loads(texto)
        except json.JSONDecodeError as exc:
            raise ValueError("El archivo JSON no es válido.") from exc
        _leer_json(datos, acc)
    else:
        _leer_tabular(texto, acc)
    if not acc.valores:
        raise ValueError("No se encontraron datos de uso con métricas COUNTER reconocidas.")
    registros = [
        {"plataforma": p, "periodo": per.isoformat(), "metrica": m, "valor": v}
        for (p, per, m), v in sorted(acc.valores.items())
    ]
    periodos = sorted({r["periodo"] for r in registros})
    return registros, {
        "filas": len(registros),
        "plataformas": sorted({r["plataforma"] for r in registros}),
        "metricas": sorted({r["metrica"] for r in registros}),
        "desde": periodos[0],
        "hasta": periodos[-1],
        "proveedor": acc.proveedor,
        "metricas_ignoradas": sorted(acc.ignoradas),
    }
