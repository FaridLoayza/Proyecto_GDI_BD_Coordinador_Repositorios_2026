"""Verificación de existencia ORCID mediante la API pública oficial."""
import os
import re
import threading
import time

import httpx


_ORCID_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]$")
_TOKEN_CACHE = {}
_TOKEN_LOCK = threading.Lock()
_TIMEOUT = httpx.Timeout(8.0, connect=4.0)


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


def _endpoints():
    environment = os.getenv("ORCID_ENVIRONMENT", "production").strip().lower()
    if environment == "sandbox":
        return "https://sandbox.orcid.org/oauth/token", "https://pub.sandbox.orcid.org/v3.0"
    if environment != "production":
        raise ValueError("ORCID_ENVIRONMENT debe ser production o sandbox.")
    return "https://orcid.org/oauth/token", "https://pub.orcid.org/v3.0"


def _access_token(client_id, client_secret, token_url):
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


def verificar(orcid):
    """Retorna resultado, referencia y nota sin guardar datos bibliográficos del perfil."""
    if not checksum_valido(orcid):
        return "no_confirmado", None, "El ORCID no supera la validación de formato y dígito de control."

    client_id = os.getenv("ORCID_CLIENT_ID", "").strip()
    client_secret = os.getenv("ORCID_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return (
            "no_disponible",
            None,
            "La consulta automática requiere ORCID_CLIENT_ID y ORCID_CLIENT_SECRET; "
            "no se realizó una llamada a ORCID.",
        )

    try:
        token_url, api_base = _endpoints()
        token = _access_token(client_id, client_secret, token_url)
        response = httpx.get(
            f"{api_base}/{orcid}/record",
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
