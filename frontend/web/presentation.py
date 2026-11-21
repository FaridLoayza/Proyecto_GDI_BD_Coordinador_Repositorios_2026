"""Presentacion HTML compartida por las rutas WSGI."""
from html import escape


class Markup(str):
    """Fragmento HTML generado internamente y listo para insertar."""


ICONOS = {
    "dashboard": '<path d="M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z"/>',
    "investigadores": '<path d="M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="10" cy="7" r="4"/><path d="M20 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    "patentes": '<path d="M6 3h9l5 5v13H6z"/><path d="M14 3v6h6M9 14h8M9 18h8"/>',
    "historico": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/><path d="M8 7h8M8 11h8"/>',
    "reportes": '<path d="M4 19V5M4 19h17"/><path d="M8 16v-5M13 16V7M18 16v-8"/>',
    "solicitudes": '<path d="M8 3h8l4 4v14H4V3z"/><path d="M8 12h8M8 16h6M16 3v5h4"/>',
    "verificado": '<path d="m5 12 4 4L19 6"/><circle cx="12" cy="12" r="10"/>',
    "salir": '<path d="M10 17l5-5-5-5M15 12H3"/><path d="M12 3h7a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-7"/>',
    "archivo": '<path d="M4 4h16v16H4z"/><path d="M8 2v4M16 2v4M4 9h16M8 13h3M8 17h7"/>',
    "buscar": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "editar": '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"/>',
    "eliminar": '<path d="M3 6h18M8 6V4h8v2M19 6l-1 15H6L5 6M10 11v6M14 11v6"/>',
    "ver": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
}


def icono(nombre):
    contenido = ICONOS.get(nombre, ICONOS["archivo"])
    return Markup(
        '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
        'aria-hidden="true" focusable="false">' + contenido + "</svg>"
    )


def _safe(value):
    if isinstance(value, Markup):
        return str(value)
    return escape("" if value is None else str(value))


def campo(nombre, etiqueta, valor="", tipo="text", requerido=False, opciones=None,
          multiple=False, filas=4, ayuda=None, readonly=False):
    requerido_attr = " required" if requerido else ""
    readonly_attr = " readonly" if readonly else ""
    help_id = f"{nombre}-ayuda"
    ayuda_html = (f'<small class="field-help" id="{escape(help_id)}">{escape(ayuda)}</small>'
                  if ayuda else "")
    if tipo == "textarea":
        control = (f'<textarea id="{escape(nombre)}" name="{escape(nombre)}" rows="{filas}"'
                   f'{requerido_attr}>{escape("" if valor is None else str(valor))}</textarea>')
    elif tipo == "select":
        seleccionado = set(valor if isinstance(valor, (list, tuple, set)) else [valor])
        multi = " multiple" if multiple else ""
        nombre_html = f'{escape(nombre)}{"[]" if multiple else ""}'
        opciones_html = []
        for item, etiqueta_opcion in (opciones or []):
            selected = " selected" if item in seleccionado or str(item) in seleccionado else ""
            opciones_html.append(
                f'<option value="{escape(str(item))}"{selected}>{escape(str(etiqueta_opcion))}</option>'
            )
        control = (f'<select id="{escape(nombre)}" name="{nombre_html}"{multi}{requerido_attr}>'
                   + "".join(opciones_html) + "</select>")
    else:
        value_attr = f' value="{escape("" if valor is None else str(valor))}"'
        control = (f'<input id="{escape(nombre)}" name="{escape(nombre)}" type="{escape(tipo)}"'
                   f'{value_attr}{requerido_attr}{readonly_attr}>')
    described = f' aria-describedby="{help_id}"' if ayuda else ""
    required_html = ' <span class="required">*</span>' if requerido else ""
    return (f'<div class="field"><label for="{escape(nombre)}">{escape(etiqueta)}'
            f'{required_html}</label>'
            f'<div class="field-control"{described}>{control}</div>{ayuda_html}</div>')


def boton(texto, estilo="primary", tipo="submit", icono_nombre=None, extra=""):
    icon_html = icono(icono_nombre) if icono_nombre else Markup("")
    return Markup(
        f'<button class="button button-{escape(estilo)}" type="{escape(tipo)}" {extra}>'
        f'{icon_html}<span>{escape(texto)}</span></button>'
    )


def tabla(encabezados, filas, vacio="No hay registros para mostrar."):
    if not filas:
        return Markup(f'<div class="empty-state"><p>{escape(vacio)}</p></div>')
    head = "".join(f"<th scope=\"col\">{escape(str(t))}</th>" for t in encabezados)
    body = []
    for fila in filas:
        celdas = "".join(f"<td>{_safe(valor)}</td>" for valor in fila)
        body.append(f"<tr>{celdas}</tr>")
    return Markup(
        '<div class="table-wrap"><table class="data-table"><thead><tr>'
        + head + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"
    )


def tarjeta(titulo, contenido, icono_nombre=None, clase=""):
    icon_html = icono(icono_nombre) if icono_nombre else Markup("")
    return Markup(
        f'<section class="card {escape(clase)}"><div class="card-heading">'
        f'{icon_html}<h2>{escape(titulo)}</h2></div><div class="card-body">{contenido}</div></section>'
    )


def estado_mensaje(mensaje, clase="info"):
    if not mensaje:
        return Markup("")
    return Markup(f'<div class="alert alert-{escape(clase)}" role="status">{escape(mensaje)}</div>')


def layout(titulo, contenido, session, csrf, mensaje=None, tipo_mensaje="success",
           activo="", status_text=""):
    coordinador = session.get("coordinador")
    investigador = session.get("investigador")
    autenticado = bool(coordinador or investigador)
    if coordinador:
        nav_items = [
            ("/dashboard", "Inicio", "dashboard"),
            ("/solicitudes", "Solicitudes", "solicitudes"),
            ("/investigadores", "Investigadores", "investigadores"),
            ("/patentes", "Patentes", "patentes"),
            ("/historico", "Histórico", "historico"),
            ("/reportes", "Reportes", "reportes"),
        ]
    elif investigador:
        nav_items = [("/investigador/inicio", "Mi solicitud", "archivo")]
        if investigador.get("estado") == "aprobado":
            nav_items.append(("/investigador/perfil", "Mi perfil", "investigadores"))
    else:
        nav_items = []
    nav_html = ""
    if autenticado:
        enlaces = []
        for href, etiqueta, nombre_icono in nav_items:
            current = " aria-current=\"page\"" if activo == href else ""
            enlaces.append(
                f'<a class="nav-link{" active" if current else ""}" href="{href}"{current}>'
                f'{icono(nombre_icono)}<span>{escape(etiqueta)}</span></a>'
            )
        nav_html = (
            '<aside class="sidebar"><div class="sidebar-label">MENÚ PRINCIPAL</div>'
            + "".join(enlaces)
            + '<form method="post" action="/logout" class="logout-form">'
            + f'<input type="hidden" name="csrf" value="{escape(csrf)}">'
            + '<button class="nav-link nav-logout" type="submit">'
            + icono("salir") + '<span>Cerrar sesión</span></button></form></aside>'
        )
    header_user = ""
    if coordinador:
        nombre = coordinador.get("nombre", "Coordinador")
        header_user = (
            '<div class="user-chip"><span class="user-avatar">C</span>'
            f'<span><strong>{escape(nombre)}</strong><small>Coordinador</small></span></div>'
        )
    elif investigador:
        correo = investigador.get("correo_elec", "Investigador")
        header_user = (
            '<div class="user-chip"><span class="user-avatar user-avatar-green">I</span>'
            f'<span><strong>{escape(correo)}</strong><small>Investigador</small></span></div>'
        )
    banner = estado_mensaje(mensaje, tipo_mensaje) if mensaje else Markup("")
    content = (
        '<div class="page-content">'
        + (f'<div class="page-status">{escape(status_text)}</div>' if status_text else "")
        + str(banner) + str(contenido) + "</div>"
    )
    return (
        "<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta name="csrf-token" content="{escape(csrf)}">'
        f"<title>{escape(titulo)} · Portal CRIS</title>"
        '<link rel="stylesheet" href="/static/css/portal.css">'
        '<script src="/static/js/portal.js" defer></script></head><body>'
        '<header class="topbar"><a class="brand" href="/">'
        '<span class="brand-mark">C</span><span class="brand-text">'
        '<strong>Portal CRIS</strong><small>Sistema de información de investigación</small>'
        '</span></a><div class="topbar-right">'
        + header_user
        + '</div></header>'
        + (f'<div class="app-shell">{nav_html}<main class="main-content">{content}</main></div>'
           if autenticado else f'<main class="public-content">{content}</main>')
        + '<footer class="footer">Sistema de información de investigación</footer>'
        + "</body></html>"
    )
