"""Cliente SUSHI (COUNTER 5) para descargar el uso de suscripciones de Elsevier.

Está APAGADO por defecto. Se activa con la sección [sushi] de config.ini
(o variables SUSHI_*) cuando la biblioteca entregue sus credenciales COUNTER:

    [sushi]
    habilitado = true
    url_base = https://api.elsevier.com/sushi
    customer_id = ...
    requestor_id = ...
    api_key = ...

Descarga el Platform Report (PR) del rango pedido y devuelve el JSON, que se
lee con el mismo lector que los archivos importados (counter.parse_counter).
"""
import configparser
import json
import os
from pathlib import Path

import httpx

from ..src.db.conexion import carpeta_base

_TIMEOUT = httpx.Timeout(60.0, connect=8.0)


class ErrorSushi(Exception):
    """La descarga SUSHI no pudo completarse; el mensaje es apto para el usuario."""


def configuracion():
    parser = configparser.ConfigParser()
    ruta = Path(carpeta_base()) / "config.ini"
    if ruta.is_file():
        parser.read(ruta, encoding="utf-8")
    ini = parser["sushi"] if parser.has_section("sushi") else {}

    def valor(clave, defecto=""):
        return os.getenv(f"SUSHI_{clave.upper()}", "").strip() or str(ini.get(clave, defecto) or defecto).strip()

    datos = {
        "habilitado": valor("habilitado", "false").lower() in ("1", "true", "si", "sí", "yes"),
        "url_base": valor("url_base", "https://api.elsevier.com/sushi").rstrip("/"),
        "customer_id": valor("customer_id"),
        "requestor_id": valor("requestor_id"),
        "api_key": valor("api_key"),
    }
    datos["listo"] = datos["habilitado"] and bool(datos["customer_id"] and datos["api_key"])
    return datos


def descargar_pr(desde, hasta):
    """Descarga el Platform Report entre dos meses 'AAAA-MM'. Devuelve bytes JSON."""
    cfg = configuracion()
    if not cfg["listo"]:
        raise ErrorSushi(
            "La descarga automática SUSHI no está activada. Importe el reporte COUNTER "
            "como archivo o configure la sección [sushi] con las credenciales de la biblioteca.")
    parametros = {
        "customer_id": cfg["customer_id"],
        "begin_date": desde,
        "end_date": hasta,
    }
    if cfg["requestor_id"]:
        parametros["requestor_id"] = cfg["requestor_id"]
    try:
        respuesta = httpx.get(
            f"{cfg['url_base']}/reports/pr",
            params=parametros,
            headers={"Accept": "application/json", "X-ELS-APIKey": cfg["api_key"]},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise ErrorSushi("No se pudo contactar el servicio SUSHI del editor.") from exc
    if respuesta.status_code != 200:
        raise ErrorSushi(f"El servicio SUSHI respondió HTTP {respuesta.status_code}.")
    try:
        datos = respuesta.json()
    except ValueError as exc:
        raise ErrorSushi("El servicio SUSHI devolvió una respuesta inválida.") from exc
    if isinstance(datos, dict) and "Report_Items" not in datos and datos.get("Code"):
        raise ErrorSushi(f"SUSHI: {datos.get('Message') or datos.get('Code')}")
    return json.dumps(datos).encode("utf-8")
