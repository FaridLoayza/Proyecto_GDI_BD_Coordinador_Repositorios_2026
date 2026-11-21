"""Integración con ORCID: login OAuth del investigador y consultas públicas.

Dos usos distintos:

- **Login OAuth (scope /authenticate):** el investigador inicia sesión en
  orcid.org con su propia contraseña y autoriza la aplicación. ORCID devuelve
  el identificador de quien autorizó, lo que prueba que el ORCID le pertenece
  (escribirlo a mano no prueba nada: cualquiera puede copiar el de otra persona).
- **Consultas públicas (scope /read-public):** comprobar que un ORCID existe
  (lo usa el coordinador) y leer sus identificadores externos públicos para
  autocompletar el Scopus Author ID.

La configuración se lee de variables de entorno ``ORCID_*`` o, si no están, de
la sección ``[orcid]`` de ``backend/config.ini``.
"""
import configparser
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx


_ORCID_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]$")
_TOKEN_CACHE = {}
_TOKEN_LOCK = threading.Lock()
_TIMEOUT = httpx.Timeout(8.0, connect=4.0)
_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.ini"
_SCOPUS_TYPE = "scopus author id"

_ENTORNOS = {
    "sandbox": ("https://sandbox.orcid.org", "https://pub.sandbox.orcid.org/v3.0"),
    "production": ("https://orcid.org", "https://pub.orcid.org/v3.0"),
}


class ErrorOrcid(Exception):
    """El login con ORCID no pudo completarse; el mensaje es apto para el usuario."""


def checksum_valido(orcid):
    if not _ORCID_PATTERN.fullmatch(orcid or ""):
        return False
    digits = orcid.replace("-", "")
    total = 0
    for digit in digits[:15]:
        total = (total + int(digit)) * 2
    remainder = (12 - total % 11) % 11
    check_digit = "X" if remainder == 10 else str(remainder)
    return digits[-1] == check_digit


def _leer_config_ini():
    parser = configparser.ConfigParser()
    path = Path(_CONFIG_PATH)
    if path.is_file():
        parser.read(path, encoding="utf-8")
    return parser["orcid"] if parser.has_section("orcid") else {}


def configuracion_oauth():
    """Configuración efectiva de ORCID (variables de entorno sobre config.ini)."""
    ini = _leer_config_ini()

    def valor(clave, defecto=""):
        env = os.getenv(f"ORCID_{clave.upper()}", "").strip()
        return env or str(ini.get(clave, defecto) or defecto).strip()

    environment = valor("environment", "production").lower()
    if environment not in _ENTORNOS:
        raise ValueError("ORCID environment debe ser production o sandbox.")
    sitio, api_base = _ENTORNOS[environment]
    client_id = valor("client_id")
    client_secret = valor("client_secret")
    redirect_uri = valor("redirect_uri")
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "environment": environment,
        "redirect_uri": redirect_uri,
        "frontend_origin": valor("frontend_origin").rstrip("/"),
        "authorize_url": f"{sitio}/oauth/authorize",
        "token_url": f"{sitio}/oauth/token",
        "api_base": api_base,
        "configurado": bool(client_id and client_secret and redirect_uri),
    }


def _access_token(client_id, client_secret, token_url):
    """Token de aplicación (/read-public), reutilizado hasta que expire."""
    key = (client_id, token_url)
    now = time.monotonic()
    with _TOKEN_LOCK:
        cached = _TOKEN_CACHE.get(key)
        if cached and cached[1] > now:
            return cached[0]
        response = httpx.post(
            token_url,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
                "scope": "/read-public",
            },
            headers={"Accept": "application/json"},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        if not isinstance(token, str) or not token or not isinstance(expires_in, (int, float)):
            raise ValueError("ORCID no devolvió un token de acceso válido.")
        _TOKEN_CACHE[key] = (token, now + max(0, float(expires_in) - 30))
        return token


def url_autorizacion(state):
    """URL de orcid.org a la que se envía al investigador para iniciar sesión."""
    config = configuracion_oauth()
    query = urlencode({
        "client_id": config["client_id"],
        "response_type": "code",
        "scope": "/authenticate",
        "redirect_uri": config["redirect_uri"],
        "state": state,
    })
    return f"{config['authorize_url']}?{query}"


def intercambiar_codigo(code):
    """Canjea el código de autorización por el ORCID real de quien inició sesión.

    Retorna ``{"orcid": str, "nombre": str | None}``. Lanza ``ErrorOrcid``.
    """
    config = configuracion_oauth()
    try:
        response = httpx.post(
            config["token_url"],
            data={
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config["redirect_uri"],
            },
            headers={"Accept": "application/json"},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError:
        raise ErrorOrcid("No se pudo contactar a ORCID. Intente nuevamente.") from None
    if response.status_code != 200:
        raise ErrorOrcid("ORCID no aceptó el inicio de sesión. Intente conectar nuevamente.")
    try:
        payload = response.json()
    except ValueError:
        raise ErrorOrcid("ORCID devolvió una respuesta inválida.") from None
    orcid_id = payload.get("orcid") if isinstance(payload, dict) else None
    if not isinstance(orcid_id, str) or not checksum_valido(orcid_id):
        raise ErrorOrcid("ORCID no devolvió un identificador válido.")
    nombre = payload.get("name")
    return {"orcid": orcid_id, "nombre": nombre.strip() if isinstance(nombre, str) and nombre.strip() else None}


def buscar_scopus_id(orcid_id):
    """Scopus Author ID publicado en los identificadores externos del ORCID, o None.

    Elsevier lo sincroniza en ORCID cuando el autor vincula su perfil de Scopus.
    Nunca lanza: si algo falla, el campo simplemente queda vacío.
    """
    try:
        config = configuracion_oauth()
        headers = {"Accept": "application/json"}
        if config["client_id"] and config["client_secret"]:
            token = _access_token(config["client_id"], config["client_secret"], config["token_url"])
            headers["Authorization"] = f"Bearer {token}"
        response = httpx.get(
            f"{config['api_base']}/{orcid_id}/external-identifiers",
            headers=headers,
            timeout=_TIMEOUT,
        )
        if response.status_code != 200:
            return None
        identificadores = response.json().get("external-identifier") or []
        for item in identificadores:
            tipo = str(item.get("external-id-type") or "").strip().lower()
            valor = str(item.get("external-id-value") or "").strip()
            if tipo == _SCOPUS_TYPE and valor.isdigit() and int(valor) > 0:
                return int(valor)
    except (httpx.HTTPError, ValueError, AttributeError, TypeError):
        return None
    return None


def verificar(orcid):
    """Retorna resultado, referencia y nota sin guardar datos bibliográficos del perfil."""
    if not checksum_valido(orcid):
        return "no_confirmado", None, "El ORCID no supera la validación de formato y dígito de control."

    try:
        config = configuracion_oauth()
    except ValueError:
        return "error_consulta", None, "La configuración de ORCID no es válida."
    if not config["client_id"] or not config["client_secret"]:
        return (
            "no_disponible",
            None,
            "La consulta automática requiere las credenciales de ORCID (client_id y "
            "client_secret); no se realizó una llamada a ORCID.",
        )

    try:
        token = _access_token(config["client_id"], config["client_secret"], config["token_url"])
        response = httpx.get(
            f"{config['api_base']}/{orcid}/record",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
            timeout=_TIMEOUT,
        )
    except (httpx.HTTPError, ValueError):
        return "error_consulta", None, "No se pudo completar la consulta ORCID. Intente más tarde."

    reference = f"https://orcid.org/{orcid}"
    if response.status_code == 200:
        return "confirmado", reference, "ORCID respondió que el registro público existe."
    if response.status_code == 404:
        return "no_confirmado", reference, "ORCID no encontró un registro público para este identificador."
    return (
        "error_consulta",
        reference,
        f"ORCID respondió HTTP {response.status_code}; el resultado requiere revisión.",
    )
