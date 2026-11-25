"""Asistente de primer inicio (lo activa el instalador de Windows).

El instalador deja en config.ini:
    [portal] configuracion_inicial = pendiente
y una contraseña aleatoria para PostgreSQL. La primera vez que se abre el
portal, el navegador muestra este asistente antes del login:

  Paso 1. Cambiar la contraseña de la base de datos por una propia
          (ALTER ROLE en PostgreSQL y luego se guarda en config.ini).
  Paso 2. Credenciales de ORCID (client_id, client_secret, entorno y URI de
          redirección). Se validan pidiendo un token a ORCID. Se puede omitir.
  Paso 3. Finalizar: configuracion_inicial = completada; no vuelve a aparecer.

Seguridad: solo responde mientras la configuración está pendiente y solo a
peticiones hechas desde la misma computadora (127.0.0.1 / ::1), con CSRF.
"""
import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..src import config_local
from ..src.db.conexion import conectar, leer_configuracion
from . import orcid

ORIGENES_LOCALES = {"127.0.0.1", "::1", "localhost"}
REDIRECT_POR_DEFECTO = "http://127.0.0.1:8000/api/auth/orcid/callback"

router = APIRouter(prefix="/api/setup")


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClaveBaseBody(_Modelo):
    nueva_clave: str = Field(min_length=12, max_length=128)
    confirmacion: str = Field(min_length=1, max_length=128)


class OrcidBody(_Modelo):
    omitir: bool = False
    client_id: str = Field(default="", max_length=40)
    client_secret: str = Field(default="", max_length=80)
    environment: str = Field(default="sandbox", pattern=r"^(sandbox|production)$")
    redirect_uri: str = Field(default=REDIRECT_POR_DEFECTO, max_length=255)


def _estado():
    parser = config_local.leer()
    return {
        "pendiente": config_local.configuracion_inicial_pendiente(),
        "paso_base_datos": parser.get("portal", "paso_base_datos", fallback="") == "hecho",
        "paso_orcid": parser.get("portal", "paso_orcid", fallback=""),
        "redirect_uri_sugerida": REDIRECT_POR_DEFECTO,
    }


def requiere_asistente_local(request: Request):
    if not config_local.configuracion_inicial_pendiente():
        raise HTTPException(status_code=409, detail="La configuración inicial ya fue completada.")
    host = request.client.host if request.client else ""
    if host not in ORIGENES_LOCALES:
        raise HTTPException(status_code=403, detail="La configuración inicial solo se puede hacer desde esta computadora.")


def _csrf(request: Request):
    # Reutiliza la protección CSRF del portal (import tardío: evita ciclo con app.py).
    from .app import require_csrf
    require_csrf(request, request.headers.get("x-csrf-token"))


@router.get("/status")
def estado():
    datos = _estado()
    return {"pendiente": datos["pendiente"]} if not datos["pendiente"] else datos


@router.post("/database", dependencies=[Depends(requiere_asistente_local), Depends(_csrf)])
def cambiar_clave_base(body: ClaveBaseBody):
    if body.nueva_clave != body.confirmacion:
        raise HTTPException(status_code=422, detail="Las contraseñas no coinciden.")
    if "'" in body.nueva_clave or "\\" in body.nueva_clave:
        raise HTTPException(status_code=422, detail="La contraseña no puede tener comillas simples ni barras invertidas.")
    cfg = leer_configuracion()
    conn = conectar(cfg)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("ALTER ROLE CURRENT_USER WITH PASSWORD %s", (body.nueva_clave,))
    except psycopg2.Error as exc:
        raise HTTPException(status_code=400, detail="PostgreSQL no aceptó el cambio de contraseña.") from exc
    finally:
        conn.close()
    config_local.actualizar("postgresql", {"password": body.nueva_clave})
    # Comprueba que la nueva contraseña ya funciona antes de dar el paso por hecho.
    conectar(dict(cfg, password=body.nueva_clave)).close()
    config_local.actualizar("portal", {"paso_base_datos": "hecho"})
    return {"ok": True}


@router.post("/orcid", dependencies=[Depends(requiere_asistente_local), Depends(_csrf)])
def guardar_orcid(body: OrcidBody):
    if body.omitir:
        config_local.actualizar("portal", {"paso_orcid": "omitido"})
        return {"ok": True, "omitido": True}
    client_id, secret, redirect = body.client_id.strip(), body.client_secret.strip(), body.redirect_uri.strip()
    if not client_id.startswith("APP-") or len(client_id) < 10:
        raise HTTPException(status_code=422, detail="El Client ID de ORCID empieza con APP- (por ejemplo APP-ABCD1234EFGH5678).")
    if len(secret) < 8:
        raise HTTPException(status_code=422, detail="Ingrese el Client secret que muestra ORCID en Developer tools.")
    if not redirect.startswith(("http://127.0.0.1", "http://localhost", "https://")):
        raise HTTPException(status_code=422, detail="La URI de redirección debe empezar con http://127.0.0.1, http://localhost o https://.")
    sitio = "https://sandbox.orcid.org" if body.environment == "sandbox" else "https://orcid.org"
    try:
        orcid._access_token(client_id, secret, f"{sitio}/oauth/token")
    except Exception as exc:  # credenciales rechazadas o ORCID inaccesible
        raise HTTPException(
            status_code=422,
            detail="ORCID no aceptó el Client ID y el Client secret. Revise que sean de la aplicación "
                   f"registrada en {sitio.replace('https://', '')} (Developer tools).",
        ) from exc
    config_local.actualizar("orcid", {
        "client_id": client_id,
        "client_secret": secret,
        "environment": body.environment,
        "redirect_uri": redirect,
        "frontend_origin": "",
    })
    config_local.actualizar("portal", {"paso_orcid": "hecho"})
    return {"ok": True}


@router.post("/finish", dependencies=[Depends(requiere_asistente_local), Depends(_csrf)])
def finalizar():
    datos = _estado()
    if not datos["paso_base_datos"]:
        raise HTTPException(status_code=409, detail="Primero cambie la contraseña de la base de datos.")
    if datos["paso_orcid"] not in ("hecho", "omitido"):
        raise HTTPException(status_code=409, detail="Configure ORCID o elija omitir ese paso.")
    config_local.actualizar("portal", {"configuracion_inicial": "completada"})
    return {"ok": True}
