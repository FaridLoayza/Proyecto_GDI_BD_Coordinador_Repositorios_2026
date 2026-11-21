"""FastAPI para la aplicación React del portal CRIS."""
import configparser
import hmac
import logging
import os
import secrets
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from ..src.db.conexion import ErrorConexion
from ..src.repositorios import (
    coordinadores,
    historico,
    investigadores,
    patentes,
    patentes_cris,
    publicaciones_candidatas,
    reportes,
)
from ..src.repositorios import solicitudes_investigador
from ..src.repositorios.catalogos import ESCUELAS_UCSM, GENEROS, ODS
from . import orcid
from . import pure_csv
from .schemas import (
    ApplicationBody,
    CandidateCurationBody,
    CandidateDecisionBody,
    CandidateDiscardBody,
    CandidateLinkBody,
    InvestigatorDecisionBody,
    LoginBody,
    ManualVerificationBody,
    ObservationBody,
    PatentBody,
    PatentDecisionBody,
    PureBatchBody,
    PureRegistrationBody,
    ReportGenerateBody,
    RegisterBody,
)

LOGGER = logging.getLogger("cris.api")
ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = ROOT / "frontend" / "portal" / "dist"
UPLOADS_DIR = ROOT / "backend" / "static" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
FOTO_MAX_BYTES = 2 * 1024 * 1024
FOTO_EXTENSIONES = {".jpg", ".jpeg", ".png"}

# Nombre legible de cada campo, para armar mensajes de validación en español.
ETIQUETAS_CAMPO = {
    "dni": "El DNI",
    "codigo_ucsm": "El código institucional",
    "correo": "El correo electrónico",
    "nombres": "Los nombres",
    "apellido_paterno": "El apellido paterno",
    "apellido_materno": "El apellido materno",
    "genero": "El género",
    "fecha_nacimiento": "La fecha de nacimiento",
    "escuela": "La escuela profesional",
    "celular": "El celular",
    "orcid": "El ORCID",
    "scopus_id": "El Scopus Author ID",
    "link_cti": "El enlace CTI Vitae",
    "resumen": "El resumen académico",
    "foto": "La foto de perfil",
    "ods": "Los ODS",
    "intereses": "Los intereses de investigación",
    "password": "La contraseña",
    "email": "El correo electrónico",
}

# Traducción de los mensajes genéricos que arma Pydantic cuando el tipo o el
# formato de un campo no es el esperado (los mensajes de negocio ya vienen en
# español porque se escriben a mano en cada field_validator).
MENSAJES_TIPO = {
    "missing": "es obligatorio.",
    "string_type": "debe ser texto.",
    "int_type": "debe ser un número entero.",
    "int_parsing": "debe ser un número entero.",
    "float_type": "debe ser un número.",
    "date_type": "debe ser una fecha válida (AAAA-MM-DD).",
    "date_parsing": "debe tener el formato de fecha AAAA-MM-DD.",
    "string_pattern_mismatch": "no tiene el formato esperado.",
    "string_too_short": "es demasiado corto.",
    "string_too_long": "es demasiado largo.",
    "too_short": "no puede estar vacío.",
    "too_long": "tiene demasiados elementos.",
    "list_type": "debe ser una lista.",
    "literal_error": "tiene un valor no permitido.",
    "greater_than": "debe ser mayor que el mínimo permitido.",
    "less_than_equal": "supera el máximo permitido.",
    "extra_forbidden": "no es un campo reconocido.",
}


def _mensaje_legible(error):
    campo = str(error["loc"][-1]) if error.get("loc") else ""
    etiqueta = ETIQUETAS_CAMPO.get(campo, campo or "Un campo")
    tipo = error.get("type", "")
    if tipo == "value_error":
        # Los field_validator ya devuelven el texto final en español.
        return error.get("msg", "").removeprefix("Value error, ")
    detalle = MENSAJES_TIPO.get(tipo, "tiene un valor inválido.")
    return f"{etiqueta} {detalle}"


def _session_secret():
    secret = os.getenv("PORTAL_SESSION_SECRET", "").strip()
    if not secret:
        config_path = ROOT / "backend" / "config.ini"
        parser = configparser.ConfigParser()
        if config_path.is_file():
            parser.read(config_path, encoding="utf-8")
        if parser.has_section("portal"):
            secret = parser.get("portal", "session_secret", fallback="").strip()
    if secret:
        if len(secret) < 32:
            raise RuntimeError("PORTAL_SESSION_SECRET debe tener al menos 32 caracteres.")
        return secret
    if os.getenv("PORTAL_ENVIRONMENT", "development").lower() == "production":
        raise RuntimeError("Configure PORTAL_SESSION_SECRET antes de iniciar en producción.")
    LOGGER.warning(
        "PORTAL_SESSION_SECRET no está configurado; se usará una clave temporal de desarrollo.")
    return secrets.token_urlsafe(48)


app = FastAPI(title="Portal CRIS UCSM", version="1.0.0")
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret(),
    session_cookie="cris_session",
    same_site="lax",
    https_only=os.getenv("PORTAL_SECURE_COOKIES", "").lower() == "true",
    max_age=8 * 60 * 60,
)

if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")


@app.exception_handler(ErrorConexion)
async def handle_database_error(_request, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_request, exc):
    mensajes = [_mensaje_legible(error) for error in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={"detail": [{"msg": mensaje} for mensaje in mensajes]},
    )


def _csrf_token(request):
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def require_csrf(request: Request, x_csrf_token: str | None = Header(default=None)):
    expected = request.session.get("csrf_token")
    if not expected or not x_csrf_token or not hmac.compare_digest(expected, x_csrf_token):
        raise HTTPException(status_code=403, detail="La sesión expiró. Recargue la página e intente otra vez.")


def _user(request, role=None):
    current = request.session.get("user")
    if not current:
        raise HTTPException(status_code=401, detail="Inicie sesión para continuar.")
    if role and current.get("role") != role:
        raise HTTPException(status_code=403, detail="No tiene permiso para esta operación.")
    return current


def _solicitud_response(solicitud):
    return {
        "id": solicitud["id"],
        "cuenta_id": solicitud["cuenta_investigador_id"],
        "estado": solicitud["estado"],
        "version": solicitud["version_actual"],
        "creada_en": solicitud["creada_en"],
        "enviada_en": solicitud["enviada_en"],
        "ultima_observacion": solicitud["ultima_observacion"],
        "formulario": solicitud["datos"],
        "verificaciones": solicitud["verificaciones"],
        "revisiones": solicitud["revisiones"],
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/catalogs")
def catalogs():
    return {"ods": ODS, "generos": GENEROS, "escuelas": ESCUELAS_UCSM}


@app.post("/api/uploads/photo", dependencies=[Depends(require_csrf)])
async def upload_photo(file: UploadFile = File(...)):
    extension = Path(file.filename or "").suffix.lower()
    if extension not in FOTO_EXTENSIONES:
        raise HTTPException(
            status_code=422,
            detail="La foto debe ser un archivo .jpg, .jpeg o .png.",
        )
    contenido = await file.read(FOTO_MAX_BYTES + 1)
    if len(contenido) > FOTO_MAX_BYTES:
        raise HTTPException(
            status_code=422,
            detail="La foto no puede superar los 2 MB.",
        )
    if not contenido:
        raise HTTPException(status_code=422, detail="El archivo de foto está vacío.")
    nombre = f"{uuid.uuid4().hex}{extension}"
    (UPLOADS_DIR / nombre).write_bytes(contenido)
    return {"foto": f"/uploads/{nombre}"}


@app.get("/api/auth/me")
def auth_me(request: Request):
    return {"user": request.session.get("user"), "csrf_token": _csrf_token(request)}


@app.post("/api/auth/login", dependencies=[Depends(require_csrf)])
def auth_login(body: LoginBody, request: Request):
    if body.role == "coordinator":
        user = coordinadores.autenticar(body.email, body.password)
        safe_user = {
            "role": "coordinator",
            "codigo_ucsm": user["codigo_ucsm"],
            "nombre": user["nombre"],
            "correo": user["correo_electronico"],
        }
    else:
        user = solicitudes_investigador.autenticar(body.email, body.password)
        safe_user = {
            "role": "investigator",
            "id": user["id"],
            "solicitud_id": user["solicitud_id"],
            "codigo_ucsm": user["codigo_ucsm"],
            "correo": user["correo_elec"],
            "estado": user["estado"],
        }
    request.session.clear()
    request.session["user"] = safe_user
    _csrf_token(request)
    return {"user": safe_user, "csrf_token": request.session["csrf_token"]}


@app.post("/api/auth/logout", dependencies=[Depends(require_csrf)])
def auth_logout(request: Request):
    request.session.clear()
    _csrf_token(request)
    return {"ok": True}


# --- Login con ORCID (OAuth, scope /authenticate) ---------------------------
# El ORCID que se guarda en la postulación es el que ORCID confirma tras el
# inicio de sesión del propio investigador, no el que se escribe en el
# formulario. El estado anti-CSRF (`state`) y el resultado viven en la sesión
# firmada del servidor (cookie cris_session); no se usa ninguna tabla.
ORCID_SESSION_KEYS = ("orcid_verificado", "orcid_nombre", "orcid_scopus_id")
ORCID_DESTINOS = {"register": "/register", "investigator": "/investigator"}


def _limpiar_orcid_sesion(request):
    for key in ORCID_SESSION_KEYS:
        request.session.pop(key, None)


@app.get("/api/auth/orcid/login")
def orcid_login(request: Request, next: str = "register"):
    config = orcid.configuracion_oauth()
    if not config["configurado"]:
        raise HTTPException(
            status_code=503,
            detail="El inicio de sesión con ORCID no está configurado en el servidor "
                   "(falta client_id, client_secret o redirect_uri).",
        )
    state = secrets.token_urlsafe(32)
    request.session["orcid_oauth_state"] = state
    request.session["orcid_oauth_next"] = next if next in ORCID_DESTINOS else "register"
    return RedirectResponse(orcid.url_autorizacion(state), status_code=307)


@app.get("/api/auth/orcid/callback")
def orcid_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    config = orcid.configuracion_oauth()
    expected = request.session.pop("orcid_oauth_state", None)
    destino = ORCID_DESTINOS[request.session.pop("orcid_oauth_next", "register")]

    def volver(resultado):
        return RedirectResponse(
            f"{config['frontend_origin']}{destino}?orcid={resultado}", status_code=307)

    # El state se consume siempre: un mismo enlace de vuelta no sirve dos veces.
    if not expected or not state or not hmac.compare_digest(expected, state):
        return volver("error")
    if error:
        return volver("cancelado")
    if not code:
        return volver("error")
    try:
        verificado = orcid.intercambiar_codigo(code)
    except orcid.ErrorOrcid as exc:
        LOGGER.warning("Login ORCID fallido: %s", exc)
        return volver("error")
    request.session["orcid_verificado"] = verificado["orcid"]
    request.session["orcid_nombre"] = verificado["nombre"]
    request.session["orcid_scopus_id"] = orcid.buscar_scopus_id(verificado["orcid"])
    return volver("ok")


@app.get("/api/auth/orcid/status")
def orcid_status(request: Request):
    try:
        configurado = orcid.configuracion_oauth()["configurado"]
    except ValueError:
        configurado = False
    return {
        "configurado": configurado,
        "orcid": request.session.get("orcid_verificado"),
        "nombre": request.session.get("orcid_nombre"),
        "scopus_id": request.session.get("orcid_scopus_id"),
    }


@app.post("/api/auth/orcid/disconnect", dependencies=[Depends(require_csrf)])
def orcid_disconnect(request: Request):
    _limpiar_orcid_sesion(request)
    return {"ok": True}


def _aplicar_orcid_de_sesion(request, payload):
    """Reemplaza ORCID y Scopus del formulario por los verificados en la sesión.

    Retorna True si había un ORCID verificado en la sesión.
    """
    verificado = request.session.get("orcid_verificado")
    if not verificado:
        return False
    scopus = request.session.get("orcid_scopus_id")
    payload["orcid"] = verificado
    payload["scopus_id"] = str(scopus) if scopus else None
    return True


@app.post("/api/researcher/register", dependencies=[Depends(require_csrf)])
def researcher_register(body: RegisterBody, request: Request):
    payload = body.application.to_procedure_payload()
    if not _aplicar_orcid_de_sesion(request, payload):
        raise HTTPException(
            status_code=409,
            detail="Conecte su cuenta ORCID antes de enviar la postulación.",
        )
    solicitudes_investigador.registrar(payload, body.password)
    user = solicitudes_investigador.autenticar(payload["correo"], body.password)
    safe_user = {
        "role": "investigator",
        "id": user["id"],
        "solicitud_id": user["solicitud_id"],
        "codigo_ucsm": user["codigo_ucsm"],
        "correo": user["correo_elec"],
        "estado": user["estado"],
    }
    request.session.clear()
    request.session["user"] = safe_user
    _csrf_token(request)
    return {"user": safe_user, "csrf_token": request.session["csrf_token"]}


@app.get("/api/researcher/application")
def researcher_application(request: Request):
    current = _user(request, "investigator")
    solicitud = solicitudes_investigador.obtener_por_cuenta(current["id"])
    if not solicitud:
        raise HTTPException(status_code=404, detail="No se encontró la solicitud de esta cuenta.")
    current.update({"solicitud_id": solicitud["id"], "estado": solicitud["estado"]})
    return _solicitud_response(solicitud)


@app.put("/api/researcher/application", dependencies=[Depends(require_csrf)])
def researcher_update_application(body: ApplicationBody, request: Request):
    current = _user(request, "investigator")
    solicitud = solicitudes_investigador.obtener_por_cuenta(current["id"])
    if not solicitud:
        raise HTTPException(status_code=404, detail="No se encontró la solicitud de esta cuenta.")
    if solicitud["estado"] != "observada":
        raise HTTPException(status_code=409, detail="Solo se pueden corregir solicitudes observadas.")
    # El DNI y el código UCSM solo se pueden corregir mientras la solicitud
    # está observada (p. ej. el coordinador indicó que el código es
    # inválido). El procedimiento valida que el nuevo valor no esté en uso
    # por otra cuenta antes de aplicarlo.
    payload = body.to_procedure_payload()
    # Si el investigador volvió a conectar ORCID se usa ese; si no, se conserva
    # el ORCID/Scopus ya guardado (se verificó al registrarse). El valor que
    # llega en el JSON nunca se usa.
    if not _aplicar_orcid_de_sesion(request, payload):
        payload["orcid"] = solicitud["codigo_orcid"]
        scopus = solicitud.get("scopus_id")
        payload["scopus_id"] = str(scopus) if scopus else None
    solicitudes_investigador.actualizar(solicitud, payload)
    _limpiar_orcid_sesion(request)
    return {"ok": True, "estado": "pendiente_revision"}


@app.get("/api/researcher/profile")
def researcher_profile(request: Request):
    current = _user(request, "investigator")
    solicitud = solicitudes_investigador.obtener_por_cuenta(current["id"])
    if not solicitud or solicitud["estado"] != "aprobada":
        raise HTTPException(status_code=403, detail="El perfil se habilita después de la aprobación.")
    profile = investigadores.obtener(solicitud["codigo_ucsm"])
    if not profile:
        raise HTTPException(status_code=404, detail="No se encontró el perfil aprobado.")
    return profile


@app.get("/api/researcher/patents")
def researcher_patents(request: Request):
    current = _user(request, "investigator")
    solicitud = solicitudes_investigador.obtener_por_cuenta(current["id"])
    if not solicitud or solicitud["estado"] != "aprobada":
        raise HTTPException(status_code=403, detail="Debe tener un perfil aprobado para solicitar patentes.")
    return patentes_cris.listar_de_investigador(solicitud["codigo_ucsm"])


@app.post("/api/researcher/patents", dependencies=[Depends(require_csrf)])
def researcher_create_patent(body: PatentBody, request: Request):
    current = _user(request, "investigator")
    solicitud = solicitudes_investigador.obtener_por_cuenta(current["id"])
    if not solicitud or solicitud["estado"] != "aprobada":
        raise HTTPException(status_code=403, detail="Debe tener un perfil aprobado para solicitar patentes.")
    patentes_cris.crear(solicitud["codigo_ucsm"], body.to_procedure_payload())
    return {"ok": True, "message": "Solicitud de patente enviada al coordinador."}


@app.put("/api/researcher/patents/{solicitud_id}", dependencies=[Depends(require_csrf)])
def researcher_update_patent(solicitud_id: int, body: PatentBody, request: Request):
    current = _user(request, "investigator")
    solicitud = solicitudes_investigador.obtener_por_cuenta(current["id"])
    patente = patentes_cris.obtener(solicitud_id)
    if not solicitud or not patente or patente["solicitante_codigo_ucsm"] != solicitud["codigo_ucsm"]:
        raise HTTPException(status_code=404, detail="No se encontró la solicitud de patente.")
    if patente["estado"] != "observada":
        raise HTTPException(status_code=409, detail="Solo se pueden corregir solicitudes observadas.")
    patentes_cris.actualizar(solicitud_id, body.to_procedure_payload())
    return {"ok": True, "estado": "pendiente_revision"}


@app.get("/api/coordinator/applications")
def coordinator_applications(request: Request):
    _user(request, "coordinator")
    return solicitudes_investigador.listar()


@app.get("/api/coordinator/dashboard")
def coordinator_dashboard(request: Request):
    _user(request, "coordinator")
    return reportes.indicadores()


@app.get("/api/coordinator/investigators")
def coordinator_investigators(request: Request, search: str = ""):
    _user(request, "coordinator")
    return [
        {
            "codigo_ucsm": row[0],
            "nombre": row[1],
            "escuela": row[2],
            "correo": row[3],
            "celular": row[4],
        }
        for row in investigadores.listar(search)
    ]


@app.get("/api/coordinator/investigators/{codigo_ucsm}")
def coordinator_investigator(codigo_ucsm: int, request: Request):
    _user(request, "coordinator")
    investigator = investigadores.obtener(codigo_ucsm)
    if not investigator:
        raise HTTPException(status_code=404, detail="No se encontró el investigador.")
    return investigator


@app.get("/api/coordinator/patent-registry")
def coordinator_patent_registry(request: Request):
    _user(request, "coordinator")
    return [
        {
            "n_patente": row[0],
            "titulo": row[1],
            "fecha_registro": row[2],
            "pais": row[3],
            "inventores": row[4],
        }
        for row in patentes.listar()
    ]


@app.get("/api/coordinator/patent-registry/{n_patente}")
def coordinator_registered_patent(n_patente: str, request: Request):
    _user(request, "coordinator")
    patent = patentes.obtener(n_patente)
    if not patent:
        raise HTTPException(status_code=404, detail="No se encontró la patente registrada.")
    return patent


@app.get("/api/coordinator/publications")
def coordinator_publications(request: Request, search: str = ""):
    _user(request, "coordinator")
    return [
        {
            "uuid": row[0],
            "titulo": row[1],
            "anio": row[2],
            "tipo": row[3],
            "idioma": row[4],
            "categoria": row[5],
        }
        for row in historico.listar(search)
    ]


async def _pure_upload(file: UploadFile):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="Seleccione un archivo CSV de Pure.")
    content = await file.read(pure_csv.MAX_BYTES + 1)
    try:
        records, summary = pure_csv.parse_pure_csv(content)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return content, records, summary


@app.post(
    "/api/coordinator/publications/import/preview",
    dependencies=[Depends(require_csrf)],
)
async def coordinator_preview_pure_import(
    request: Request, file: UploadFile = File(...)
):
    _user(request, "coordinator")
    _, _, summary = await _pure_upload(file)
    return summary


@app.post(
    "/api/coordinator/publications/import",
    dependencies=[Depends(require_csrf)],
)
async def coordinator_import_pure(
    request: Request, file: UploadFile = File(...)
):
    current = _user(request, "coordinator")
    content, records, parsed = await _pure_upload(file)
    result = publicaciones_candidatas.importar_pure(
        records, file.filename, current["codigo_ucsm"], content)
    automatic = None
    batch = None
    if result["candidatas_en_lote"]:
        automatic = publicaciones_candidatas.aprobar_lote_pure(
            result["lote_sha256"], current["codigo_ucsm"])
        batch = publicaciones_candidatas.resumen_lote_pure(result["lote_sha256"])
    return {
        **parsed,
        **result,
        "consolidacion_automatica": automatic,
        "revision_lote": batch,
    }


@app.post(
    "/api/coordinator/publications/import/bulk-approve",
    dependencies=[Depends(require_csrf)],
)
def coordinator_bulk_approve_pure(body: PureBatchBody, request: Request):
    current = _user(request, "coordinator")
    return publicaciones_candidatas.aprobar_lote_pure(
        body.lote_sha256, current["codigo_ucsm"])


@app.get("/api/coordinator/publications/candidates")
def coordinator_publication_candidates(
    request: Request,
    search: str = Query(default="", max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    _user(request, "coordinator")
    return publicaciones_candidatas.listar(search, limit, offset)


@app.get("/api/coordinator/publications/candidates/{candidate_id}")
def coordinator_publication_candidate(candidate_id: int, request: Request):
    _user(request, "coordinator")
    candidate = publicaciones_candidatas.obtener(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="No se encontró la candidatura de Pure.")
    return candidate


@app.put(
    "/api/coordinator/publications/candidates/{candidate_id}/curation",
    dependencies=[Depends(require_csrf)],
)
def coordinator_curate_publication_candidate(
    candidate_id: int, body: CandidateCurationBody, request: Request
):
    current = _user(request, "coordinator")
    lote_sha256 = publicaciones_candidatas.guardar_curacion(
        candidate_id, body.model_dump(), current["codigo_ucsm"])
    automatic = None
    if lote_sha256:
        automatic = publicaciones_candidatas.aprobar_lote_pure(
            lote_sha256, current["codigo_ucsm"])
    return {"ok": True, "consolidacion_automatica": automatic}


@app.post(
    "/api/coordinator/publications/candidates/{candidate_id}/discard",
    dependencies=[Depends(require_csrf)],
)
def coordinator_discard_publication_candidate(
    candidate_id: int, body: CandidateDiscardBody, request: Request
):
    current = _user(request, "coordinator")
    publicaciones_candidatas.descartar(
        candidate_id, current["codigo_ucsm"], body.motivo)
    return {"ok": True, "estado": "descartada"}


@app.post(
    "/api/coordinator/publications/candidates/{candidate_id}/investigators",
    dependencies=[Depends(require_csrf)],
)
def coordinator_link_candidate_investigator(
    candidate_id: int, body: CandidateLinkBody, request: Request
):
    current = _user(request, "coordinator")
    publicaciones_candidatas.vincular_investigador(
        candidate_id, body.codigo_ucsm, current["codigo_ucsm"])
    return {"ok": True}


@app.post(
    "/api/coordinator/publications/candidates/{candidate_id}/investigators/"
    "{codigo_ucsm}/decision",
    dependencies=[Depends(require_csrf)],
)
def coordinator_decide_candidate_link(
    candidate_id: int,
    codigo_ucsm: int,
    body: CandidateDecisionBody,
    request: Request,
):
    current = _user(request, "coordinator")
    publicaciones_candidatas.resolver_vinculo(
        candidate_id, codigo_ucsm, current["codigo_ucsm"],
        body.resultado, body.motivo,
    )
    return {"ok": True, "estado": body.resultado}


@app.get("/api/coordinator/publications/{publication_uuid}")
def coordinator_publication(publication_uuid: str, request: Request):
    _user(request, "coordinator")
    publication = historico.obtener(publication_uuid)
    if not publication:
        raise HTTPException(status_code=404, detail="No se encontró la publicación.")
    return {
        "uuid": publication["uuid"],
        "formulario": historico.para_formulario(publication),
    }


@app.get("/api/coordinator/reports/catalog")
def coordinator_report_catalog(request: Request):
    _user(request, "coordinator")
    return [
        {"id": report_id, "titulo": title, "usa_join": uses_join}
        for report_id, title, uses_join in reportes.catalogo()
    ]


@app.get("/api/coordinator/reports/queries/{report_id}")
def coordinator_run_report_query(report_id: int, request: Request):
    _user(request, "coordinator")
    if report_id not in {item[0] for item in reportes.catalogo()}:
        raise HTTPException(status_code=404, detail="No existe esa consulta.")
    title, columns, rows = reportes.ejecutar(report_id)
    return {"titulo": title, "columnas": columns, "filas": rows}


@app.get("/api/coordinator/reports/issued")
def coordinator_issued_reports(request: Request):
    _user(request, "coordinator")
    return [
        {"fecha": row[0], "coordinador": row[1]}
        for row in reportes.emitidos()
    ]


@app.get("/api/coordinator/reports/issued/{fecha}")
def coordinator_issued_report_detail(fecha: str, request: Request):
    _user(request, "coordinator")
    return {"fecha": fecha, "detalle": reportes.detalle(fecha)}


@app.post(
    "/api/coordinator/reports/issued",
    dependencies=[Depends(require_csrf)],
)
def coordinator_generate_report(body: ReportGenerateBody, request: Request):
    current = _user(request, "coordinator")
    reportes.generar(body.fecha, current["codigo_ucsm"])
    return {"ok": True, "fecha": body.fecha}


@app.get("/api/coordinator/applications/{solicitud_id}")
def coordinator_application(solicitud_id: int, request: Request):
    _user(request, "coordinator")
    solicitud = solicitudes_investigador.obtener(solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="No se encontró la solicitud.")
    return _solicitud_response(solicitud)


@app.post(
    "/api/coordinator/applications/{solicitud_id}/orcid-check",
    dependencies=[Depends(require_csrf)],
)
def coordinator_orcid_check(solicitud_id: int, request: Request):
    current = _user(request, "coordinator")
    solicitud = solicitudes_investigador.obtener(solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="No se encontró la solicitud.")
    if solicitud["estado"] != "pendiente_revision":
        raise HTTPException(status_code=409, detail="ORCID se consulta en una solicitud pendiente.")
    resultado, referencia, nota = orcid.verificar(solicitud["codigo_orcid"])
    solicitudes_investigador.registrar_verificacion(
        solicitud_id, solicitud["version_actual"], "orcid", "api",
        resultado, None, referencia, nota,
    )
    return {"fuente": "orcid", "resultado": resultado, "referencia": referencia, "nota": nota}


@app.post(
    "/api/coordinator/applications/{solicitud_id}/manual-verifications",
    dependencies=[Depends(require_csrf)],
)
def coordinator_manual_verification(
    solicitud_id: int, body: ManualVerificationBody, request: Request
):
    current = _user(request, "coordinator")
    solicitud = solicitudes_investigador.obtener(solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="No se encontró la solicitud.")
    if solicitud["estado"] != "pendiente_revision":
        raise HTTPException(status_code=409, detail="La solicitud ya no está pendiente de revisión.")
    solicitudes_investigador.registrar_verificacion(
        solicitud_id, solicitud["version_actual"], body.fuente, "manual",
        body.resultado, current["codigo_ucsm"], body.referencia, body.nota,
    )
    return {"ok": True}


@app.post(
    "/api/coordinator/applications/{solicitud_id}/observation",
    dependencies=[Depends(require_csrf)],
)
def coordinator_observe_application(
    solicitud_id: int, body: ObservationBody, request: Request
):
    current = _user(request, "coordinator")
    solicitudes_investigador.observar(
        solicitud_id, current["codigo_ucsm"], body.motivo)
    return {"ok": True, "estado": "observada"}


@app.post(
    "/api/coordinator/applications/{solicitud_id}/decision",
    dependencies=[Depends(require_csrf)],
)
def coordinator_decide_application(
    solicitud_id: int, body: InvestigatorDecisionBody, request: Request
):
    current = _user(request, "coordinator")
    solicitudes_investigador.resolver(
        solicitud_id, current["codigo_ucsm"], body.resultado, body.motivo)
    return {"ok": True, "estado": body.resultado}


@app.get("/api/coordinator/pure-pending")
def coordinator_pure_pending(request: Request):
    _user(request, "coordinator")
    return solicitudes_investigador.perfiles_pure_pendientes()


@app.post(
    "/api/coordinator/investigators/{codigo_ucsm}/pure",
    dependencies=[Depends(require_csrf)],
)
def coordinator_register_pure(
    codigo_ucsm: int, body: PureRegistrationBody, request: Request
):
    current = _user(request, "coordinator")
    solicitudes_investigador.registrar_pure(
        codigo_ucsm, body.pure_person_id, current["codigo_ucsm"])
    return {"ok": True, "pure_estado": "registrado_manual"}


@app.get("/api/coordinator/patents")
def coordinator_patents(request: Request):
    _user(request, "coordinator")
    return patentes_cris.listar()


@app.get("/api/coordinator/patents/{solicitud_id}")
def coordinator_patent(solicitud_id: int, request: Request):
    _user(request, "coordinator")
    solicitud = patentes_cris.obtener(solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="No se encontró la solicitud de patente.")
    return solicitud


@app.post(
    "/api/coordinator/patents/{solicitud_id}/decision",
    dependencies=[Depends(require_csrf)],
)
def coordinator_decide_patent(
    solicitud_id: int, body: PatentDecisionBody, request: Request
):
    current = _user(request, "coordinator")
    patentes_cris.resolver(
        solicitud_id, current["codigo_ucsm"], body.resultado, body.motivo)
    return {"ok": True, "estado": body.resultado}


@app.get("/")
def frontend_index():
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "La interfaz React aún no está compilada. En desarrollo, inicie "
                      "el servidor Vite en frontend/portal con npm run dev."
        },
    )


@app.get("/{path:path}")
def frontend_route(path: str):
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Ruta API no encontrada.")
    candidate = (FRONTEND_DIST / path).resolve()
    if candidate.is_relative_to(FRONTEND_DIST.resolve()) and candidate.is_file():
        return FileResponse(candidate)
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="No se encontró la ruta solicitada.")
