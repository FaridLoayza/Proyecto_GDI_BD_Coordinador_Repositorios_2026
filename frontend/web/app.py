"""Portal WSGI sin framework, construido sobre la biblioteca estandar de Python."""
import logging
import os
import re
import secrets
import threading
import time
from datetime import date
from http import cookies
from urllib.parse import parse_qs
from wsgiref.simple_server import WSGIServer, make_server
from socketserver import ThreadingMixIn

from backend.src.db.conexion import ErrorConexion
from backend.src.repositorios import (
    coordinadores, historico, investigadores, patentes, reportes, solicitudes_investigador,
)
from backend.src.repositorios.catalogos import CATEGORIAS, GENEROS, IDIOMAS, ODS, TIPOS_PUBLICACION

from .presentation import Markup, boton, campo, icono, layout, tabla, tarjeta

LOGGER = logging.getLogger("portal")
MAX_BODY = 1024 * 1024
SESSION_TTL = 8 * 60 * 60
STATIC_FILES = {
    "/static/css/portal.css": ("static/css/portal.css", "text/css; charset=utf-8"),
    "/static/js/portal.js": ("static/js/portal.js", "text/javascript; charset=utf-8"),
}
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class PortalResponse:
    def __init__(self, body="", status="200 OK", content_type="text/html; charset=utf-8",
                 headers=()):
        self.body = body.encode("utf-8") if isinstance(body, str) else body
        self.status = status
        self.content_type = content_type
        self.headers = list(headers)


class Request:
    def __init__(self, environ):
        self.environ = environ
        self.method = environ.get("REQUEST_METHOD", "GET").upper()
        self.path = environ.get("PATH_INFO", "/")
        self.query = parse_qs(environ.get(
            "QUERY_STRING", ""), keep_blank_values=True)
        self.form = {}
        self.too_large = False
        if self.method == "POST":
            try:
                length = int(environ.get("CONTENT_LENGTH") or "0")
            except ValueError:
                length = MAX_BODY + 1
            if length < 0 or length > MAX_BODY:
                self.too_large = True
            else:
                raw = environ["wsgi.input"].read(length)
                charset = environ.get("CONTENT_TYPE", "").lower()
                if "application/x-www-form-urlencoded" not in charset:
                    self.form = {}
                else:
                    decoded = raw.decode("utf-8", errors="replace")
                    self.form = parse_qs(decoded, keep_blank_values=True)

    def get(self, name, default=""):
        values = self.form.get(name)
        return values[-1] if values else default

    def query_get(self, name, default=""):
        values = self.query.get(name)
        return values[-1] if values else default

    def getlist(self, name):
        return self.form.get(name, [])


class SessionStore:
    def __init__(self):
        self._data = {}
        self._lock = threading.RLock()

    def open(self, environ):
        cookie = cookies.SimpleCookie()
        try:
            cookie.load(environ.get("HTTP_COOKIE", ""))
        except cookies.CookieError:
            cookie = cookies.SimpleCookie()
        morsel = cookie.get("portal_session")
        session_id = morsel.value if morsel else ""
        now = time.time()
        with self._lock:
            expired = [key for key, entry in self._data.items()
                       if entry["expires"] <= now]
            for key in expired:
                del self._data[key]
            entry = self._data.get(session_id)
            if not entry or entry["expires"] <= now:
                session_id = secrets.token_urlsafe(32)
                entry = {"expires": now + SESSION_TTL,
                         "csrf": secrets.token_urlsafe(32)}
                self._data[session_id] = entry
                dirty = True
            else:
                entry["expires"] = now + SESSION_TTL
                dirty = False
            return session_id, entry, dirty

    def replace(self, old_id):
        now = time.time()
        session_id = secrets.token_urlsafe(32)
        entry = {"expires": now + SESSION_TTL,
                 "csrf": secrets.token_urlsafe(32)}
        with self._lock:
            self._data.pop(old_id, None)
            self._data[session_id] = entry
        return session_id, entry

    def close(self, session_id):
        with self._lock:
            self._data.pop(session_id, None)


class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class PortalApplication:
    def __init__(self):
        self.sessions = SessionStore()

    def __call__(self, environ, start_response):
        request = Request(environ)
        session_id, session, cookie_dirty = self.sessions.open(environ)
        request.session_id = session_id
        request.session = session
        request.cookie_dirty = cookie_dirty
        try:
            if request.too_large:
                response = self._message(
                    request, "La solicitud excede el tamaño permitido.", "413 Payload Too Large")
            elif request.path in STATIC_FILES and request.method == "GET":
                response = self._static(request.path)
            else:
                response = self._dispatch(request)
        except ErrorConexion as exc:
            response = self._message(request, str(
                exc), "400 Bad Request", "error")
        except Exception:
            LOGGER.exception("Error inesperado en la ruta %s", request.path)
            response = self._message(
                request,
                "Ocurrió un error inesperado. Intente nuevamente o consulte el registro del servidor.",
                "500 Internal Server Error",
                "error",
            )
        headers = [
            ("Content-Type", response.content_type),
            ("Content-Length", str(len(response.body))),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "same-origin"),
            ("Content-Security-Policy",
             "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; "
             "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"),
            ("Cache-Control", "no-store"),
        ]
        headers.extend(response.headers)
        if request.cookie_dirty:
            headers.append(("Set-Cookie", self._cookie(request.session_id)))
        start_response(response.status, headers)
        return [response.body]

    def _static(self, path):
        relative, content_type = STATIC_FILES[path]
        with open(os.path.join(BASE_DIR, relative), "rb") as asset:
            return PortalResponse(asset.read(), content_type=content_type)

    @staticmethod
    def _cookie(session_id):
        secure = "; Secure" if os.environ.get(
            "PORTAL_HTTPS", "").lower() in ("1", "true", "yes") else ""
        return (f"portal_session={session_id}; Path=/; Max-Age={SESSION_TTL}; "
                f"HttpOnly; SameSite=Lax{secure}")

    def _dispatch(self, request):
        if request.method not in ("GET", "POST"):
            return self._message(request, "Método no permitido.", "405 Method Not Allowed", "error")
        if request.method == "POST" and not self._csrf_valid(request):
            return self._message(request, "La sesión del formulario expiró. Recargue la página.", "403 Forbidden", "error")

        if request.path == "/" and request.method == "GET":
            return self._home(request)
        if request.path == "/login":
            return self._login(request)
        if request.path == "/investigador/registro":
            return self._investigador_registro(request)
        if request.path == "/investigador/login":
            return self._investigador_login(request)
        if request.path == "/logout" and request.method == "POST":
            request.session.clear()
            request.session_id, request.session = self.sessions.replace(
                request.session_id)
            request.cookie_dirty = True
            return self._redirect("/")

        if request.session.get("coordinador"):
            if request.path.startswith("/investigador/"):
                return self._redirect("/dashboard")
            if request.path.startswith("/solicitudes"):
                return self._solicitudes(request)
            if request.path == "/dashboard" and request.method == "GET":
                return self._dashboard(request)
            if request.path.startswith("/investigadores"):
                return self._investigadores(request)
            if request.path.startswith("/patentes"):
                return self._patentes(request)
            if request.path.startswith("/historico"):
                return self._historico(request)
            if request.path.startswith("/reportes"):
                return self._reportes(request)
            return self._message(request, "No se encontró la página solicitada.",
                                 "404 Not Found", "error")

        if request.session.get("investigador"):
            if not request.path.startswith("/investigador/"):
                return self._redirect("/investigador/inicio")
            if request.path == "/investigador/inicio" and request.method == "GET":
                return self._investigador_inicio(request)
            if request.path == "/investigador/solicitud/editar":
                return self._investigador_editar_solicitud(request)
            if request.path == "/investigador/perfil" and request.method == "GET":
                return self._investigador_perfil(request)
            return self._message(request, "No se encontró la página solicitada.",
                                 "404 Not Found", "error")

        if request.path.startswith("/investigador/"):
            return self._redirect("/investigador/login")
        return self._redirect("/login")

    @staticmethod
    def _csrf_valid(request):
        expected = request.session.get("csrf", "")
        supplied = request.get("csrf")
        return bool(expected and supplied and secrets.compare_digest(expected, supplied))

    @staticmethod
    def _redirect(location):
        return PortalResponse("", "303 See Other", headers=(("Location", location),))

    def _page(self, request, title, content, status="200 OK", active=""):
        flash = request.session.pop("flash", None)
        message, kind = flash if flash else (None, "success")
        body = layout(title, content, request.session, request.session.get("csrf", ""),
                      message, kind, active)
        return PortalResponse(body, status)

    def _message(self, request, message, status, kind="info"):
        content = (
            '<section class="page-heading"><div><div class="eyebrow">Portal CRIS</div>'
            f'<h1>{self._escape_title(status)}</h1></div></section>'
            f'<div class="alert alert-{self._escape(kind)}" role="status">{self._escape(message)}</div>'
            '<div class="button-row"><a class="button button-secondary" href="/">Volver al inicio</a></div>'
        )
        return self._page(request, "Aviso", content, status, "/")

    @staticmethod
    def _escape(value):
        from html import escape
        return escape(str(value))

    @staticmethod
    def _escape_title(status):
        from html import escape
        return escape(status.split(" ", 1)[-1])

    def _home(self, request):
        if request.session.get("coordinador"):
            return self._redirect("/dashboard")
        if request.session.get("investigador"):
            return self._redirect("/investigador/inicio")
        content = (
            '<section class="home-hero">'
            '<div class="home-copy"><div class="eyebrow">Sistema de información de investigación</div>'
            '<h1>Portal de Investigación</h1>'
            '<p>Un espacio para registrar y gestionar la información de investigación de la Universidad.</p>'
            '<div class="home-points"><span>' + str(icono("verificado")) +
            '<span>Acceso según tu perfil</span></span><span>' + str(icono("archivo")) +
            '<span>Información centralizada</span></span></div></div>'
            '<div class="home-mark" aria-hidden="true"><span class="home-mark-ring">'
            + str(icono("dashboard")) +
            '</span><span class="home-mark-caption">INVESTIGACIÓN</span></div>'
            '</section>'
            '<section class="access-section"><div class="section-intro">'
            '<div class="eyebrow">Elige tu tipo de acceso</div><h2>¿Cómo deseas ingresar?</h2>'
            '<p>Selecciona el perfil que corresponde a tu función.</p></div>'
            '<div class="portal-options">'
            '<article class="portal-option role-researcher"><div class="role-icon">'
            + str(icono("investigadores")) + '</div><div class="role-content">'
            '<span class="role-kicker">Para docentes e investigadores</span><h3>Investigador</h3>'
            '<p>Registra tu solicitud y consulta su estado. El acceso completo se habilita tras la validación del coordinador.</p>'
            '<div class="role-actions"><a class="button button-green" href="/investigador/registro">Crear cuenta</a>'
            '<a class="text-link" href="/investigador/login">Ya tengo una cuenta</a></div></div></article>'
            '<article class="portal-option role-coordinator"><div class="role-icon">'
            + str(icono("dashboard")) + '</div><div class="role-content">'
            '<span class="role-kicker">Gestión institucional</span><h3>Coordinador de repositorios</h3>'
            '<p>Administra investigadores, patentes, histórico de publicaciones y reportes.</p>'
            '<div class="role-actions"><a class="button button-primary" href="/login">Ingresar al portal</a>'
            '<span class="text-note">Acceso institucional</span></div></div></article>'
            '</div></section>'
        )
        return self._page(request, "Inicio", content)

    def _login(self, request):
        if request.session.get("coordinador"):
            return self._redirect("/dashboard")
        if request.session.get("investigador"):
            return self._redirect("/investigador/inicio")
        error = ""
        if request.method == "POST":
            try:
                coord = coordinadores.autenticar(
                    request.get("correo"), request.get("clave"))
            except ErrorConexion as exc:
                error = str(exc)
            else:
                request.session_id, request.session = self.sessions.replace(
                    request.session_id)
                request.session["coordinador"] = coord
                request.cookie_dirty = True
                return self._redirect("/dashboard")
        warning = (f'<div class="alert alert-error" role="alert">{self._escape(error)}</div>'
                   if error else "")
        content = (
            '<div class="login-wrap"><section class="card"><div class="card-body">'
            '<div class="eyebrow">Acceso administrativo</div><h1 class="login-title">Iniciar sesión</h1>'
            '<p class="login-intro">Ingrese con las credenciales del coordinador de repositorios.</p>'
            + warning
            + '<form method="post" action="/login">'
            + self._csrf_field(request)
            + '<div class="field-grid">'
            + campo("correo", "Correo institucional",
                    tipo="email", requerido=True)
            + campo("clave", "Contraseña", tipo="password", requerido=True)
            + '</div><div class="button-row">'
            + str(boton("Ingresar", "primary"))
            + '</div></form></div></section></div>'
            + '<p class="auth-switch">¿Buscabas el acceso de investigador? '
            '<a href="/investigador/login">Ingresar como investigador</a>.</p>'
        )
        return self._page(request, "Iniciar sesión", content)

    def _investigador_registro(self, request):
        if request.session.get("coordinador"):
            return self._redirect("/dashboard")
        if request.session.get("investigador"):
            return self._redirect("/investigador/inicio")
        error = ""
        if request.method == "POST":
            clave = request.get("clave")
            if clave != request.get("confirmar_clave"):
                error = "Las contraseñas no coinciden."
            else:
                try:
                    datos = self._investigador_payload(request)
                    solicitudes_investigador.registrar(datos, clave)
                    cuenta = solicitudes_investigador.autenticar(
                        datos["correo"], clave)
                except ErrorConexion as exc:
                    error = str(exc)
                else:
                    request.session_id, request.session = self.sessions.replace(
                        request.session_id)
                    request.session["investigador"] = cuenta
                    request.cookie_dirty = True
                    self._flash(
                        request, "Cuenta creada. Tu solicitud está pendiente de validación.")
                    return self._redirect("/investigador/inicio")

        fields = self._investigador_campos(request, {})
        values = request.form
        password = values.get("clave", [""])[0]
        confirmation = values.get("confirmar_clave", [""])[0]
        warning = (f'<div class="alert alert-error" role="alert">{self._escape(error)}</div>'
                   if error else "")
        body = (
            warning + '<form method="post" class="auth-form">'
            + self._csrf_field(request)
            + '<section class="form-section"><div class="form-section-heading">'
            '<span class="step-number">1</span><div><h2>Datos personales y académicos</h2>'
            '<p>Usaremos estos datos para crear tu solicitud de registro.</p></div></div>'
            '<div class="field-grid">' +
            "".join(str(field) for field in fields) + '</div></section>'
            '<section class="form-section"><div class="form-section-heading">'
            '<span class="step-number">2</span><div><h2>Seguridad de la cuenta</h2>'
            '<p>Usa una contraseña de al menos 12 caracteres.</p></div></div>'
            '<div class="field-grid">'
            + campo("clave", "Contraseña", password, "password", True)
            + campo("confirmar_clave", "Confirmar contraseña",
                    confirmation, "password", True)
            + '</div></section><div class="button-row">'
            + str(boton("Enviar solicitud", "green", icono_nombre="verificado"))
            + '<a class="button button-secondary" href="/">Cancelar</a></div></form>'
        )
        content = (
            self._heading("Crear cuenta de investigador",
                          "Completa tu información para enviar la solicitud al coordinador.")
            + str(tarjeta("Registro de investigador",
                  Markup(body), clase="form-card"))
            + '<p class="auth-switch">¿Ya tienes una cuenta? '
            '<a href="/investigador/login">Inicia sesión</a>.</p>'
        )
        return self._page(request, "Crear cuenta", content)

    def _investigador_login(self, request):
        if request.session.get("coordinador"):
            return self._redirect("/dashboard")
        if request.session.get("investigador"):
            return self._redirect("/investigador/inicio")
        error = ""
        if request.method == "POST":
            try:
                cuenta = solicitudes_investigador.autenticar(
                    request.get("correo"), request.get("clave"))
            except ErrorConexion as exc:
                error = str(exc)
            else:
                request.session_id, request.session = self.sessions.replace(
                    request.session_id)
                request.session["investigador"] = cuenta
                request.cookie_dirty = True
                return self._redirect("/investigador/inicio")
        warning = (f'<div class="alert alert-error" role="alert">{self._escape(error)}</div>'
                   if error else "")
        content = (
            '<div class="login-wrap"><section class="card form-card"><div class="card-body">'
            '<div class="eyebrow">Acceso de investigador</div><h1 class="login-title">Bienvenido</h1>'
            '<p class="login-intro">Ingresa para consultar el estado de tu solicitud.</p>'
            + warning + '<form method="post" action="/investigador/login">'
            + self._csrf_field(request) + '<div class="field-grid">'
            + campo("correo", "Correo electrónico",
                    request.get("correo"), "email", True)
            + campo("clave", "Contraseña", "", "password", True)
            + '</div><div class="button-row">'
            + str(boton("Ingresar", "green"))
            + '</div></form></div></section></div>'
            '<p class="auth-switch">¿Aún no tienes cuenta? '
            '<a href="/investigador/registro">Crear cuenta de investigador</a>.</p>'
        )
        return self._page(request, "Acceso de investigador", content)

    def _investigador_inicio(self, request):
        cuenta_id = request.session["investigador"]["id"]
        solicitud = solicitudes_investigador.obtener(cuenta_id)
        if not solicitud:
            request.session.pop("investigador", None)
            return self._redirect("/investigador/login")
        request.session["investigador"].update({
            "estado": solicitud["estado"],
            "correo_elec": solicitud["correo_elec"],
            "codigo_ucsm": solicitud["codigo_ucsm"],
        })
        if solicitud["estado"] == "pendiente":
            status_card = (
                '<div class="status-banner status-pending"><span class="status-dot"></span>'
                '<div><strong>Solicitud en revisión</strong><p>El coordinador revisará los datos antes de habilitar tu perfil.</p></div></div>'
                '<p class="muted">Mientras esté pendiente, solo podrás consultar el estado de tu solicitud.</p>'
            )
        elif solicitud["estado"] == "observado":
            status_card = (
                '<div class="status-banner status-observed"><span class="status-dot"></span>'
                '<div><strong>Necesitamos una corrección</strong>'
                f'<p>{self._escape(solicitud["observacion"] or "")}</p></div></div>'
                '<p class="muted">Actualiza los datos indicados y vuelve a enviar la solicitud.</p>'
                '<a class="button button-green" href="/investigador/solicitud/editar">'
                + str(icono("editar")) + '<span>Corregir solicitud</span></a>'
            )
        else:
            status_card = (
                '<div class="status-banner status-approved"><span class="status-dot"></span>'
                '<div><strong>Perfil validado</strong>'
                '<p>Tu cuenta está activa y el registro ya se encuentra en el repositorio.</p></div></div>'
                '<a class="button button-green" href="/investigador/perfil">'
                + str(icono("investigadores")) +
                '<span>Ver mi perfil</span></a>'
            )
        content = (
            self._heading("Mi solicitud",
                          "Aquí puedes consultar el estado de tu registro.")
            + str(tarjeta("Estado de registro",
                  Markup(status_card), clase="status-card"))
        )
        return self._page(request, "Mi solicitud", content, active="/investigador/inicio")

    def _investigador_editar_solicitud(self, request):
        cuenta_id = request.session["investigador"]["id"]
        solicitud = solicitudes_investigador.obtener(cuenta_id)
        if not solicitud or solicitud["estado"] != "observado":
            return self._redirect("/investigador/inicio")
        if request.method == "POST":
            try:
                solicitudes_investigador.actualizar(
                    cuenta_id, self._investigador_payload(request))
            except ErrorConexion as exc:
                error = str(exc)
            else:
                request.session["investigador"]["estado"] = "pendiente"
                self._flash(
                    request, "Correcciones enviadas. Tu solicitud volvió a revisión.")
                return self._redirect("/investigador/inicio")
        else:
            error = ""
        fields = self._investigador_campos(
            request, solicitud["datos"], identidad_bloqueada=True)
        warning = (f'<div class="alert alert-error" role="alert">{self._escape(error)}</div>'
                   if error else "")
        body = (
            warning + '<form method="post">' + self._csrf_field(request)
            + '<div class="field-grid">' +
            "".join(str(field) for field in fields) + '</div>'
            + '<div class="button-row">' +
            str(boton("Enviar correcciones", "green"))
            + '<a class="button button-secondary" href="/investigador/inicio">Cancelar</a></div></form>'
        )
        content = self._heading(
            "Corregir solicitud", "Revisa las observaciones y actualiza los campos indicados.")
        content += str(tarjeta("Datos de la solicitud",
                       Markup(body), clase="form-card"))
        return self._page(request, "Corregir solicitud", content,
                          active="/investigador/inicio")

    def _investigador_perfil(self, request):
        cuenta_id = request.session["investigador"]["id"]
        solicitud = solicitudes_investigador.obtener(cuenta_id)
        if not solicitud or solicitud["estado"] != "aprobado":
            return self._redirect("/investigador/inicio")
        datos = investigadores.obtener(solicitud["codigo_ucsm"])
        if not datos:
            return self._message(request, "No se encontró el perfil asociado a esta cuenta.",
                                 "404 Not Found", "error")
        fields = [
            ("Código institucional", datos["codigo_ucsm"]), ("DNI", datos["dni"]),
            ("Nombre", " ".join(
                (datos["nombres"], datos["apellido_paterno"], datos["apellido_materno"]))),
            ("Escuela", datos["escuela"]), ("Correo", datos["correo"]),
            ("ORCID", datos["orcid"]), ("Scopus ID", datos["scopus_id"]),
            ("CTI Vitae", datos["link_cti"]), ("ODS", ", ".join(datos["ods"])),
            ("Intereses", datos["intereses"]),
        ]
        details = "".join(
            f"<dt>{self._escape(label)}</dt><dd>{self._escape(value)}</dd>"
            for label, value in fields
        )
        content = self._heading(
            "Mi perfil", "Datos registrados en el repositorio.")
        content += str(tarjeta("Perfil de investigador",
                       Markup(f'<dl class="details-grid">{details}</dl>')))
        return self._page(request, "Mi perfil", content, active="/investigador/perfil")

    def _investigador_payload(self, request):
        return {
            "dni": request.get("dni"),
            "nombres": request.get("nombres"),
            "apellido_paterno": request.get("apellido_paterno"),
            "apellido_materno": request.get("apellido_materno"),
            "genero": request.get("genero"),
            "fecha_nacimiento": request.get("fecha_nacimiento"),
            "codigo_ucsm": request.get("codigo_ucsm"),
            "escuela": request.get("escuela"),
            "celular": request.get("celular"),
            "correo": request.get("correo"),
            "orcid": request.get("orcid"),
            "scopus_id": request.get("scopus_id"),
            "link_cti": request.get("link_cti"),
            "foto": request.get("foto"),
            "resumen": request.get("resumen"),
            "ods": request.getlist("ods[]"),
            "intereses": request.get("intereses"),
        }

    def _investigador_campos(self, request, data, identidad_bloqueada=False,
                             escuelas=None):
        values = request.form

        def val(key, default=""):
            return values.get(key, [data.get(key, default)])[0]

        selected_ods = values.get("ods[]", data.get("ods", []))
        if isinstance(selected_ods, str):
            selected_ods = [selected_ods]
        if escuelas is None:
            campo_escuela = campo(
                "escuela", "Escuela profesional", val("escuela"), requerido=True)
        else:
            campo_escuela = campo(
                "escuela", "Escuela profesional", val(
                    "escuela"), "select", True,
                [(escuela, escuela) for escuela in escuelas],
            )
        return (
            campo("dni", "DNI", val("dni"), requerido=True,
                  readonly=identidad_bloqueada),
            campo("nombres", "Nombres", val("nombres"), requerido=True),
            campo("apellido_paterno", "Apellido paterno",
                  val("apellido_paterno"), requerido=True),
            campo("apellido_materno", "Apellido materno",
                  val("apellido_materno"), requerido=True),
            campo("genero", "Género", val("genero"), "select", True,
                  [(genero, genero) for genero in GENEROS]),
            campo("fecha_nacimiento", "Fecha de nacimiento",
                  val("fecha_nacimiento"), "date", True),
            campo("codigo_ucsm", "Código institucional", val("codigo_ucsm"),
                  requerido=True, readonly=identidad_bloqueada),
            campo_escuela,
            campo("celular", "Celular", val("celular"), "tel", True),
            campo("correo", "Correo electrónico",
                  val("correo"), "email", True),
            campo("orcid", "ORCID", val("orcid"), requerido=True),
            campo("scopus_id", "Scopus ID", val("scopus_id"), "number", True),
            campo("link_cti", "Enlace CTI Vitae",
                  val("link_cti"), "url", True),
            campo("foto", "Foto de perfil (.jpg/.png)",
                  val("foto"), requerido=True),
            campo("resumen", "Resumen académico", val(
                "resumen"), "textarea", True, filas=3),
            campo("ods", "ODS", selected_ods, "select", True, [(ods, ods) for ods in ODS],
                  multiple=True, ayuda="Puedes seleccionar varios; usa Ctrl o Cmd."),
            campo("intereses", "Intereses de investigación", val("intereses"), "textarea", True,
                  filas=2, ayuda="Separa los intereses con coma."),
        )

    def _dashboard(self, request):
        data = reportes.indicadores()
        resumen = coordinadores.resumen(
            request.session["coordinador"]["codigo_ucsm"])
        metrics = [
            ("Investigadores", data["investigadores"]),
            ("Escuelas", data["escuelas"]),
            ("Publicaciones", data["publicaciones"]),
            ("Patentes", data["patentes"]),
            ("ODS vinculados", data["ods_vinculados"]),
        ]
        metric_html = "".join(
            f'<section class="metric"><div class="metric-label">{self._escape(label)}</div>'
            f'<div class="metric-value">{self._escape(value)}</div></section>'
            for label, value in metrics
        )
        ranking = tabla(["ODS", "Asociaciones"],
                        data["ranking_ods"], "No hay ODS registrados.")
        escuelas = tabla(["Escuela profesional", "Investigadores"], data["top_escuelas"],
                         "No hay investigadores registrados.")
        content = (
            '<section class="page-heading"><div><div class="eyebrow">Resumen institucional</div>'
            f'<h1>Bienvenido, {self._escape(request.session["coordinador"].get("nombre", "Coordinador"))}</h1>'
            '<p>Indicadores actuales del repositorio de investigación.</p></div></section>'
            f'<div class="metric-grid">{metric_html}</div>'
            '<div class="two-column">'
            + str(tarjeta("Ranking de ODS", ranking, "reportes"))
            + str(tarjeta("Escuelas con más investigadores",
                  escuelas, "investigadores"))
            + '</div><section class="card"><div class="card-body">'
            f'<p class="muted">Reportes emitidos: <strong>{resumen["reportes"]}</strong>'
            f' · Por usted: <strong>{resumen["mis_reportes"]}</strong></p>'
            '<form method="post" action="/reportes/generar">'
            + self._csrf_field(request)
            + campo("fecha", "Fecha del reporte",
                    date.today().isoformat(), "date", True)
            + '<div class="button-row">'
            + str(boton("Generar reporte de hoy",
                  "primary", icono_nombre="reportes"))
            + '</div></form></div></section>'
        )
        return self._page(request, "Dashboard", content, active="/dashboard")

    def _investigadores(self, request):
        if request.path == "/investigadores" and request.method == "GET":
            filtro = request.query_get("q")
            rows = []
            for codigo, nombre, escuela, correo, celular in investigadores.listar(filtro):
                actions = (
                    '<div class="actions">'
                    f'<a class="table-link" href="/investigadores/{codigo}/editar">{icono("editar")}Editar</a>'
                    f'<form method="post" action="/investigadores/{codigo}/eliminar" '
                    'data-confirm="¿Eliminar este investigador? Esta acción no se puede deshacer.">'
                    + self._csrf_field(request)
                    + f'<button class="button button-danger button-small" type="submit">{icono("eliminar")}Eliminar</button>'
                    '</form></div>'
                )
                rows.append((codigo, nombre, escuela, correo,
                            celular, Markup(actions)))
            form = (
                '<form class="search-bar" method="get" action="/investigadores">'
                f'<input class="search-input" name="q" value="{self._escape(filtro)}" '
                'placeholder="Buscar por nombre o código" aria-label="Buscar investigadores">'
                + str(boton("Buscar", "secondary", icono_nombre="buscar"))
                + '</form>'
            )
            content = (
                self._heading("Investigadores", "Registros actuales de investigadores y sus formatos.",
                              '<a class="button button-primary" href="/investigadores/nuevo">'
                              + str(icono("plus")) + '<span>Nuevo investigador</span></a>')
                + str(tarjeta("Listado de investigadores",
                              Markup(form + str(tabla(["Código", "Investigador", "Escuela", "Correo",
                                                       "Celular", "Acciones"], rows)))))
            )
            return self._page(request, "Investigadores", content, active="/investigadores")

        if request.path == "/investigadores/nuevo":
            return self._investigador_form(request, None)
        match = re.fullmatch(
            r"/investigadores/(\d+)(?:/(editar|eliminar))?", request.path)
        if not match:
            return self._message(request, "No se encontró el investigador solicitado.", "404 Not Found", "error")
        codigo, action = match.group(1), match.group(2)
        if action == "eliminar" and request.method == "POST":
            investigadores.eliminar(codigo)
            self._flash(request, "Investigador eliminado.")
            return self._redirect("/investigadores")
        if action == "editar":
            return self._investigador_form(request, codigo)
        if request.method == "GET":
            datos = investigadores.obtener(codigo)
            if not datos:
                return self._message(request, "No existe ese investigador.", "404 Not Found", "error")
            fields = [
                ("Código institucional", datos["codigo_ucsm"]), ("DNI", datos["dni"]),
                ("Nombre", " ".join(
                    (datos["nombres"], datos["apellido_paterno"], datos["apellido_materno"]))),
                ("Escuela", datos["escuela"]), ("Correo", datos["correo"]),
                ("ORCID", datos["orcid"]), ("Scopus ID", datos["scopus_id"]),
                ("CTI Vitae", datos["link_cti"]
                 ), ("ODS", ", ".join(datos["ods"])),
            ]
            info = "".join(
                f"<dt>{self._escape(k)}</dt><dd>{self._escape(v)}</dd>" for k, v in fields)
            content = self._heading("Detalle de investigador", f"Código institucional {codigo}.") + str(
                tarjeta("Información", Markup(f'<dl class="details-grid">{info}</dl>')))
            return self._page(request, "Detalle de investigador", content, active="/investigadores")
        return self._message(request, "Método no permitido.", "405 Method Not Allowed", "error")

    def _investigador_form(self, request, codigo):
        editing = codigo is not None
        data = investigadores.obtener(codigo) if editing else {}
        if editing and not data:
            return self._message(request, "No existe ese investigador.", "404 Not Found", "error")
        escuelas = investigadores.escuelas()
        if request.method == "POST":
            payload = self._investigador_payload(request)
            if editing:
                investigadores.modificar(codigo, payload)
            else:
                investigadores.registrar(
                    payload, request.session["coordinador"]["codigo_ucsm"])
            self._flash(request, "Investigador guardado correctamente.")
            return self._redirect("/investigadores")

        fields = self._investigador_campos(
            request, data, identidad_bloqueada=editing, escuelas=escuelas)
        if editing:
            fields += (Markup(
                '<div class="notice field-span">El DNI y el código institucional no se pueden cambiar desde este formulario.</div>'
            ),)
        body = (
            '<form method="post">'
            + self._csrf_field(request)
            + '<div class="field-grid">' +
            "".join(str(f) for f in fields) + '</div>'
            + '<div class="button-row">' + str(boton("Guardar", "primary"))
            + '<a class="button button-secondary" href="/investigadores">Cancelar</a></div></form>'
        )
        title = "Editar investigador" if editing else "Nuevo investigador"
        content = self._heading(
            title, "Complete los datos del formato existente.")
        content += str(tarjeta(title, Markup(body)))
        return self._page(request, title, content, active="/investigadores")

    def _solicitudes(self, request):
        if request.path == "/solicitudes" and request.method == "GET":
            rows = []
            for solicitud_id, correo, dni, codigo, estado, creado in solicitudes_investigador.listar():
                link = Markup(
                    f'<a class="table-link" href="/solicitudes/{solicitud_id}">'
                    f'{self._escape(estado.title())} · Revisar</a>'
                )
                rows.append((creado, correo, dni, codigo, link))
            content = (
                self._heading("Solicitudes de investigador",
                              "Revisa los registros enviados. Al aprobar, se crea el perfil con el procedimiento existente.")
                + str(tarjeta("Bandeja de solicitudes",
                              tabla(["Fecha", "Correo", "DNI", "Código institucional", "Estado / acción"], rows,
                                    "No hay solicitudes por revisar.")))
            )
            return self._page(request, "Solicitudes", content, active="/solicitudes")

        match = re.fullmatch(
            r"/solicitudes/(\d+)(?:/(aprobar|observar))?", request.path)
        if not match:
            return self._message(request, "No se encontró la solicitud.", "404 Not Found", "error")
        solicitud_id, action = int(match.group(1)), match.group(2)
        solicitud = solicitudes_investigador.obtener(solicitud_id)
        if not solicitud:
            return self._message(request, "No existe esa solicitud.", "404 Not Found", "error")
        coordinador = request.session["coordinador"]["codigo_ucsm"]
        if action == "aprobar" and request.method == "POST":
            solicitudes_investigador.aprobar(solicitud_id, coordinador)
            self._flash(
                request, "Solicitud aprobada y perfil creado correctamente.")
            return self._redirect("/solicitudes")
        if action == "observar" and request.method == "POST":
            solicitudes_investigador.observar(
                solicitud_id, coordinador, request.get("observacion"))
            self._flash(
                request, "Se enviaron las observaciones al investigador.")
            return self._redirect("/solicitudes")
        if request.method != "GET":
            return self._message(request, "Método no permitido.",
                                 "405 Method Not Allowed", "error")

        data = solicitud["datos"]
        labels = [
            ("DNI", data.get("dni")), ("Código institucional", data.get("codigo_ucsm")),
            ("Nombres", data.get("nombres")), ("Apellido paterno",
                                               data.get("apellido_paterno")),
            ("Apellido materno", data.get("apellido_materno")
             ), ("Género", data.get("genero")),
            ("Fecha de nacimiento", data.get("fecha_nacimiento")
             ), ("Escuela", data.get("escuela")),
            ("Celular", data.get("celular")), ("Correo", data.get("correo")),
            ("ORCID", data.get("orcid")), ("Scopus ID", data.get("scopus_id")),
            ("CTI Vitae", data.get("link_cti")), ("Foto", data.get("foto")),
            ("Resumen", data.get("resumen")), ("ODS",
                                               ", ".join(data.get("ods", []))),
            ("Intereses", data.get("intereses")),
        ]
        details = "".join(
            f"<dt>{self._escape(label)}</dt><dd>{self._escape(value)}</dd>"
            for label, value in labels
        )
        review_controls = ""
        if solicitud["estado"] == "pendiente":
            review_controls = (
                '<div class="review-actions"><form method="post" '
                f'action="/solicitudes/{solicitud_id}/aprobar" '
                'data-confirm="¿Aprobar la solicitud y crear el perfil de investigador?">'
                + self._csrf_field(request)
                + str(boton("Aprobar solicitud", "green", icono_nombre="verificado"))
                + '</form><form method="post" class="observation-form" '
                f'action="/solicitudes/{solicitud_id}/observar">'
                + self._csrf_field(request)
                + campo("observacion", "Observaciones para el investigador", tipo="textarea",
                        requerido=True, filas=3)
                + str(boton("Solicitar correcciones",
                      "secondary", icono_nombre="editar"))
                + '</form></div>'
            )
        content = (
            self._heading("Revisión de solicitud",
                          f"Solicitud #{solicitud_id} · {solicitud['estado'].title()}")
            + str(tarjeta("Datos enviados", Markup(f'<dl class="details-grid">{details}</dl>'),
                          clase="form-card"))
            + review_controls
            + '<a class="button button-secondary" href="/solicitudes">Volver a la bandeja</a>'
        )
        return self._page(request, "Revisión de solicitud", content, active="/solicitudes")

    def _patentes(self, request):
        if request.path == "/patentes" and request.method == "GET":
            rows = []
            for numero, titulo, fecha, pais, inventores in patentes.listar():
                actions = (
                    '<div class="actions">'
                    f'<a class="table-link" href="/patentes/{self._url(numero)}/editar">{icono("editar")}Editar</a>'
                    f'<form method="post" action="/patentes/{self._url(numero)}/eliminar" '
                    'data-confirm="¿Eliminar esta patente? Esta acción no se puede deshacer.">'
                    + self._csrf_field(request)
                    + f'<button class="button button-danger button-small" type="submit">{icono("eliminar")}Eliminar</button>'
                    '</form></div>'
                )
                rows.append((numero, titulo, fecha, pais,
                            inventores, Markup(actions)))
            content = (
                self._heading("Patentes", "Formatos de patente registrados y sus inventores.",
                              '<a class="button button-primary" href="/patentes/nueva">'
                              + str(icono("plus")) + '<span>Nueva patente</span></a>')
                + str(tarjeta("Listado de patentes",
                              tabla(["N.º patente", "Título", "Fecha", "País", "Inventores", "Acciones"], rows)))
            )
            return self._page(request, "Patentes", content, active="/patentes")

        if request.path == "/patentes/nueva":
            return self._patente_form(request, None)
        match = re.fullmatch(
            r"/patentes/([^/]+)(?:/(editar|eliminar))?", request.path)
        if not match:
            return self._message(request, "No se encontró la patente solicitada.", "404 Not Found", "error")
        numero, action = self._unquote(match.group(1)), match.group(2)
        if action == "eliminar" and request.method == "POST":
            patentes.eliminar(numero)
            self._flash(request, "Patente eliminada.")
            return self._redirect("/patentes")
        if action == "editar":
            return self._patente_form(request, numero)
        if request.method == "GET":
            data = patentes.obtener(numero)
            if not data:
                return self._message(request, "No existe esa patente.", "404 Not Found", "error")
            info = "".join(
                f"<dt>{self._escape(k)}</dt><dd>{self._escape(v)}</dd>"
                for k, v in (("Número", data["n_patente"]), ("Título", data["titulo"]),
                             ("Editorial", data["editorial"]
                              ), ("Fecha", data["fecha_registro"]),
                             ("CIP", data["cip"]), ("País", data["pais"]),
                             ("Inventores", ", ".join(
                                 map(str, data["inventores"]))),
                             ("Clasificación OCDE", data["ocde"]))
            )
            content = self._heading("Detalle de patente", numero) + str(
                tarjeta("Información", Markup(f'<dl class="details-grid">{info}</dl>')))
            return self._page(request, "Detalle de patente", content, active="/patentes")
        return self._message(request, "Método no permitido.", "405 Method Not Allowed", "error")

    def _patente_form(self, request, numero):
        editing = numero is not None
        data = patentes.obtener(numero) if editing else {}
        if editing and not data:
            return self._message(request, "No existe esa patente.", "404 Not Found", "error")
        opciones = investigadores.opciones()
        if request.method == "POST":
            payload = {
                "n_patente": request.get("n_patente"),
                "titulo": request.get("titulo"),
                "editorial": request.get("editorial"),
                "fecha_registro": request.get("fecha_registro"),
                "cip": request.get("cip"),
                "pais": request.get("pais"),
                "inventores": request.getlist("inventores[]"),
                "ocde": request.get("ocde"),
            }
            if editing:
                patentes.modificar(numero, payload)
            else:
                patentes.registrar(
                    payload, request.session["coordinador"]["codigo_ucsm"])
            self._flash(request, "Patente guardada correctamente.")
            return self._redirect("/patentes")
        values = request.form if request.method == "POST" else {}

        def val(key, default=""):
            return values.get(key, [data.get(key, default)])[0]
        selected = values.get("inventores[]", data.get("inventores", []))
        fields = [
            campo("n_patente", "Número de patente", val(
                "n_patente"), requerido=not editing),
            campo("titulo", "Título", val("titulo"), requerido=True),
            campo("editorial", "Editorial", val("editorial"), requerido=True),
            campo("fecha_registro", "Fecha de registro",
                  val("fecha_registro"), "date", True),
            campo("cip", "CIP", val("cip"), requerido=True),
            campo("pais", "País", val("pais"), requerido=True),
            campo("inventores", "Inventores (seleccione uno o más)", selected, "select", True,
                  opciones, multiple=True, ayuda="Solo se pueden elegir investigadores ya registrados."),
            campo("ocde", "Clasificación OCDE (campo | objetivo, una línea por combinación)",
                  val("ocde"), "textarea", True, filas=4),
        ]
        body = (
            '<form method="post">' + self._csrf_field(request)
            + '<div class="field-grid">' +
            "".join(str(f) for f in fields) + '</div>'
            + '<div class="button-row">' + str(boton("Guardar", "primary"))
            + '<a class="button button-secondary" href="/patentes">Cancelar</a></div></form>'
        )
        title = "Editar patente" if editing else "Nueva patente"
        return self._page(request, title,
                          self._heading(
                              title, "Complete los datos del formato de patente.")
                          + str(tarjeta(title, Markup(body))),
                          active="/patentes")

    def _historico(self, request):
        if request.path == "/historico" and request.method == "GET":
            filtro = request.query_get("q")
            rows = []
            for uid, titulo, anio, tipo, idioma, categoria in historico.listar(filtro):
                actions = (
                    '<div class="actions">'
                    f'<a class="table-link" href="/historico/{self._url(uid)}/editar">{icono("editar")}Editar</a>'
                    f'<form method="post" action="/historico/{self._url(uid)}/eliminar" '
                    'data-confirm="¿Eliminar esta publicación? Esta acción no se puede deshacer.">'
                    + self._csrf_field(request)
                    + f'<button class="button button-danger button-small" type="submit">{icono("eliminar")}Eliminar</button>'
                    '</form></div>'
                )
                rows.append((uid, titulo, anio, tipo, idioma,
                            categoria, Markup(actions)))
            search = (
                '<form class="search-bar" method="get" action="/historico">'
                f'<input class="search-input" name="q" value="{self._escape(filtro)}" '
                'placeholder="Buscar por título" aria-label="Buscar publicaciones">'
                + str(boton("Buscar", "secondary", icono_nombre="buscar"))
                + '</form>'
            )
            content = (
                self._heading("Histórico de publicaciones",
                              "Registros científicos actuales; la importación CSV no forma parte de esta fase.",
                              '<a class="button button-primary" href="/historico/nuevo">'
                              + str(icono("plus")) + '<span>Nueva publicación</span></a>')
                + str(tarjeta("Publicaciones", Markup(search + str(tabla(
                    ["UUID", "Título", "Año", "Tipo", "Idioma", "Categoría", "Acciones"], rows)))))
            )
            return self._page(request, "Histórico", content, active="/historico")
        if request.path == "/historico/nuevo":
            return self._historico_form(request, None)
        match = re.fullmatch(
            r"/historico/([^/]+)(?:/(editar|eliminar))?", request.path)
        if not match:
            return self._message(request, "No se encontró la publicación solicitada.", "404 Not Found", "error")
        uid, action = self._unquote(match.group(1)), match.group(2)
        if action == "eliminar" and request.method == "POST":
            historico.eliminar(uid)
            self._flash(request, "Publicación eliminada.")
            return self._redirect("/historico")
        if action == "editar":
            return self._historico_form(request, uid)
        if request.method == "GET":
            data = historico.obtener(uid)
            if not data:
                return self._message(request, "No existe esa publicación.", "404 Not Found", "error")
            values = historico.para_formulario(data)
            info = "".join(
                f"<dt>{self._escape(k)}</dt><dd>{self._escape(v)}</dd>"
                for k, v in (("UUID", uid), ("Título", values["title"]),
                             ("Año", values["publication_year"]
                              ), ("Tipo", values["type"]),
                             ("Idioma", values["language"]))
            )
            content = self._heading("Detalle de publicación", uid) + str(
                tarjeta("Información", Markup(f'<dl class="details-grid">{info}</dl>')))
            return self._page(request, "Detalle de publicación", content, active="/historico")
        return self._message(request, "Método no permitido.", "405 Method Not Allowed", "error")

    def _historico_form(self, request, uid):
        editing = uid is not None
        original = historico.obtener(uid) if editing else {}
        if editing and not original:
            return self._message(request, "No existe esa publicación.", "404 Not Found", "error")
        data = historico.para_formulario(original) if editing else {}
        if request.method == "POST":
            payload = {
                "title": request.get("title"),
                "publication_year": request.get("publication_year"),
                "type": request.get("type"),
                "language": request.get("language"),
                "category": request.get("category"),
                "volumen": request.get("volumen"),
                "number_of_pages": request.get("number_of_pages"),
                "pages": request.get("pages"),
                "portal_url": request.get("portal_url"),
                "abstract": request.get("abstract"),
                "contributors": request.get("contributors"),
                "identifiers": request.get("identifiers"),
                "keywords_groups": request.get("keywords_groups"),
            }
            historico.guardar(payload, request.session["coordinador"]["codigo_ucsm"],
                              uuid_existente=uid)
            self._flash(request, "Publicación guardada correctamente.")
            return self._redirect("/historico")
        values = request.form if request.method == "POST" else {}

        def val(key, default=""):
            return values.get(key, [data.get(key, default)])[0]
        fields = [
            campo("title", "Título", val("title"), requerido=True),
            campo("publication_year", "Año de publicación",
                  val("publication_year"), "number", True),
            campo("type", "Tipo de publicación", val("type", "Article"), "select", True,
                  [(x, x) for x in TIPOS_PUBLICACION]),
            campo("language", "Idioma", val("language", "English"), "select", True,
                  [(x, x) for x in IDIOMAS]),
            campo("category", "Categoría", val("category", "Research"), "select", True,
                  [(x, x) for x in CATEGORIAS]),
            campo("volumen", "Volumen (opcional)", val("volumen"), "number"),
            campo("number_of_pages", "Total de páginas (opcional)",
                  val("number_of_pages"), "number"),
            campo("pages", "Páginas", val("pages")),
            campo("portal_url", "URL del portal",
                  val("portal_url"), "url", True),
            campo("abstract", "Resumen", val("abstract"), "textarea", filas=4),
            campo("contributors", "Contribuyentes (uno por línea)",
                  val("contributors"), "textarea", True, filas=3),
            campo("identifiers", "Identificadores (separados por ;)",
                  val("identifiers")),
            campo("keywords_groups", "Palabras clave (separadas por ;)",
                  val("keywords_groups")),
        ]
        body = (
            '<form method="post">' + self._csrf_field(request)
            + '<div class="field-grid">' +
            "".join(str(f) for f in fields) + '</div>'
            + '<div class="button-row">' + str(boton("Guardar", "primary"))
            + '<a class="button button-secondary" href="/historico">Cancelar</a></div></form>'
        )
        title = "Editar publicación" if editing else "Nueva publicación"
        return self._page(request, title,
                          self._heading(
                              title, "Complete los campos editables del registro histórico.")
                          + str(tarjeta(title, Markup(body))),
                          active="/historico")

    def _reportes(self, request):
        if request.path == "/reportes/generar" and request.method == "POST":
            reportes.generar(request.get("fecha"),
                             request.session["coordinador"]["codigo_ucsm"])
            self._flash(request, "Reporte generado correctamente.")
            return self._redirect("/reportes")
        if request.path == "/reportes/detalle" and request.method == "GET":
            texto = reportes.detalle(request.query_get("fecha"))
            content = (
                self._heading("Detalle del reporte",
                              request.query_get("fecha"))
                + str(tarjeta("Resultado",
                      Markup(f'<pre class="report-output">{self._escape(texto)}</pre>')))
                + '<a class="button button-secondary" href="/reportes">Volver a reportes</a>'
            )
            return self._page(request, "Detalle del reporte", content, active="/reportes")
        if request.path != "/reportes" or request.method != "GET":
            return self._message(request, "No se encontró el reporte solicitado.", "404 Not Found", "error")
        selected = request.query_get("consulta")
        result = ""
        if selected:
            try:
                query_id = int(selected)
            except ValueError:
                return self._message(request, "La consulta seleccionada no es válida.",
                                     "400 Bad Request", "error")
            titulo, columns, rows = reportes.ejecutar(query_id)
            result = str(tarjeta(titulo, tabla(
                columns, rows, "La consulta no devolvió resultados.")))
        emitted = []
        for fecha, coordinador in reportes.emitidos():
            action = Markup(
                f'<a class="table-link" href="/reportes/detalle?fecha={self._url(fecha)}">Ver detalle</a>')
            emitted.append((fecha, coordinador, action))
        queries = reportes.catalogo()
        options = [("<option value=\"\">Seleccione una consulta</option>")]
        for query_id, title, uses_join in queries:
            chosen = " selected" if str(query_id) == selected else ""
            join = " · JOIN" if uses_join else ""
            options.append(
                f'<option value="{query_id}"{chosen}>{self._escape(f"{query_id:02d} · {title}{join}")
                                                      }</option>'
            )
        query_form = (
            '<form method="get" action="/reportes" class="report-selector"><div class="field">'
            '<label for="consulta">Consulta de solo lectura</label>'
            '<select id="consulta" name="consulta">' +
            "".join(options) + '</select></div>'
            + str(boton("Ejecutar consulta", "primary"))
            + '</form>'
        )
        content = (
            self._heading(
                "Reportes", "Consultas de lectura y cortes históricos del dashboard.")
            + str(tarjeta("Catálogo de consultas", Markup(query_form)))
            + result
            + str(tarjeta("Reportes emitidos",
                  tabla(["Fecha", "Coordinador", "Acción"], emitted)))
        )
        return self._page(request, "Reportes", content, active="/reportes")

    def _heading(self, title, description, action=""):
        return Markup(
            '<section class="page-heading"><div><div class="eyebrow">Portal CRIS</div>'
            f'<h1>{self._escape(title)}</h1><p>{self._escape(description)}</p></div>'
            + str(action) + "</section>"
        )

    @staticmethod
    def _csrf_field(request):
        from html import escape
        return f'<input type="hidden" name="csrf" value="{escape(request.session.get("csrf", ""))}">'

    @staticmethod
    def _flash(request, message, kind="success"):
        request.session["flash"] = (message, kind)

    @staticmethod
    def _url(value):
        from urllib.parse import quote
        return quote(str(value), safe="")

    @staticmethod
    def _unquote(value):
        from urllib.parse import unquote
        return unquote(value)


application = PortalApplication()


def ejecutar():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    host = os.environ.get("PORTAL_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("PORTAL_PORT", "8000"))
    except ValueError as exc:
        raise SystemExit("PORTAL_PORT debe ser un puerto numérico.") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("PORTAL_PORT debe estar entre 1 y 65535.")
    with make_server(host, port, application, server_class=ThreadedWSGIServer) as server:
        LOGGER.info(
            "Portal disponible en http://%s:%s (servidor de desarrollo)", host, port)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            LOGGER.info("Cierre del servidor solicitado.")
