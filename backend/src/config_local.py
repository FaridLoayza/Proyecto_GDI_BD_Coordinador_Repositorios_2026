"""Lectura y escritura de config.ini conservando comentarios y orden.

configparser pierde los comentarios al guardar; aquí se cambian solo las
líneas "clave = valor" pedidas y, si faltan, se agregan al final de su sección
(o se crea la sección). Lo usan el asistente de primer inicio y el instalador.
"""
import configparser
import os
import re
import tempfile

from .db.conexion import carpeta_base


def ruta_config():
    return os.path.join(carpeta_base(), "config.ini")


def leer(ruta=None):
    parser = configparser.ConfigParser()
    ruta = ruta or ruta_config()
    if os.path.isfile(ruta):
        parser.read(ruta, encoding="utf-8")
    return parser


def _limpiar(valor):
    texto = str(valor)
    if "\n" in texto or "\r" in texto:
        raise ValueError("Los valores de configuración no pueden tener saltos de línea.")
    return texto.strip()


def actualizar(seccion, valores, ruta=None):
    """Escribe valores en [seccion] de config.ini de forma atómica."""
    ruta = ruta or ruta_config()
    lineas = []
    if os.path.isfile(ruta):
        with open(ruta, encoding="utf-8") as archivo:
            lineas = archivo.read().splitlines()
    pendientes = {clave: _limpiar(valor) for clave, valor in valores.items()}
    actual = None
    fin_seccion = None
    for i, linea in enumerate(lineas):
        encabezado = re.match(r"^\s*\[([^\]]+)\]\s*$", linea)
        if encabezado:
            if actual == seccion:
                fin_seccion = i
            actual = encabezado.group(1).strip()
            continue
        if actual != seccion:
            continue
        clave = re.match(r"^\s*([A-Za-z0-9_]+)\s*[=:]", linea)
        if clave and clave.group(1) in pendientes:
            nombre = clave.group(1)
            lineas[i] = f"{nombre} = {pendientes.pop(nombre)}"
    if actual == seccion and fin_seccion is None:
        fin_seccion = len(lineas)
    if pendientes:
        nuevas = [f"{clave} = {valor}" for clave, valor in pendientes.items()]
        if fin_seccion is None:
            lineas += ([""] if lineas and lineas[-1].strip() else []) + [f"[{seccion}]"] + nuevas
        else:
            while fin_seccion > 0 and not lineas[fin_seccion - 1].strip():
                fin_seccion -= 1
            lineas[fin_seccion:fin_seccion] = nuevas
    carpeta = os.path.dirname(os.path.abspath(ruta))
    descriptor, temporal = tempfile.mkstemp(dir=carpeta, prefix=".config-", suffix=".tmp")
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
        archivo.write("\n".join(lineas) + "\n")
    os.replace(temporal, ruta)


def configuracion_inicial_pendiente(ruta=None):
    """True solo si el instalador marcó [portal] configuracion_inicial = pendiente."""
    parser = leer(ruta)
    return parser.get("portal", "configuracion_inicial", fallback="").strip().lower() == "pendiente"
