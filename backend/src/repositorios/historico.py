"""CRUD del historico de publicaciones con sp_cargar_historico (inserta o actualiza)
y sp_eliminar_historico (borrado logico). El procedimiento recibe 33 parametros: aqui se piden al
usuario solo los esenciales y el resto se completa con valores por defecto."""
import hashlib
import uuid as _uuid
from datetime import date

from psycopg2.extras import Json

from ..db.conexion import consultar_dicts, ejecutar_procedimiento
from . import utilidades as u
from .catalogos import TIPOS_PUBLICACION

# Orden EXACTO de los parametros de sp_cargar_historico
ORDEN = [
    "uuid", "title", "publication_year", "type", "volumen", "create_date", "journal_number",
    "create_by", "version", "number_of_pages", "modified_by", "abstract", "total_contributors",
    "peer_review", "pages", "type_discriminator", "bibliographical_note", "visibility",
    "modified_date", "submission_year", "system_name", "portal_url", "sub_title", "language",
    "category", "coordinador", "fecha_reporte", "contributors", "identifiers",
    "electronic_versions", "keywords_groups", "publication_status", "links",
]
ARRAYS = ("contributors", "identifiers", "electronic_versions", "keywords_groups",
          "publication_status")

_SQL_LISTAR = """
SELECT h.uuid::text AS uuid, h.title, h.publication_year, h.type, h.language, h.category,
       h.activo, h.fecha_baja, h.motivo_baja
FROM historico h
{filtro}
ORDER BY h.publication_year DESC, h.title
"""

_SQL_OBTENER = """
SELECT h.*, h.uuid::text AS uuid_texto,
  COALESCE((SELECT array_agg(c.contributors ORDER BY c.contributors)
              FROM historico_contributors c WHERE c.uuid = h.uuid), '{}') AS contributors,
  COALESCE((SELECT array_agg(i.identifiers ORDER BY i.identifiers)
              FROM historico_identifiers i WHERE i.uuid = h.uuid), '{}') AS identifiers,
  COALESCE((SELECT array_agg(e.electronic_versions ORDER BY e.electronic_versions)
              FROM historico_electronic_versions e WHERE e.uuid = h.uuid), '{}') AS electronic_versions,
  COALESCE((SELECT array_agg(k.keywords_groups ORDER BY k.keywords_groups)
              FROM historico_keywords_groups k WHERE k.uuid = h.uuid), '{}') AS keywords_groups,
  COALESCE((SELECT array_agg(s.publication_status ORDER BY s.publication_status)
              FROM historico_publication_status s WHERE s.uuid = h.uuid), '{}') AS publication_status,
  COALESCE((SELECT jsonb_agg(jsonb_build_object('pure_id', l.pure_id, 'link_type', l.link_type,
                                               'url', l.url, 'description', l.description))
              FROM historico_links l WHERE l.uuid = h.uuid), '[]'::jsonb) AS links
FROM historico h
WHERE h.uuid = %s::uuid
"""


def listar_detalle(filtro="", estado="activos"):
    """Diccionarios del catalogo de publicaciones. estado: activos | bajas | todos."""
    condiciones, parametros = [], []
    filtro = (filtro or "").strip()
    if filtro:
        condiciones.append("h.title ILIKE %s")
        parametros.append(f"%{filtro}%")
    condicion_estado = u.condicion_estado(estado, "h")
    if condicion_estado:
        condiciones.append(condicion_estado)
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    return consultar_dicts(_SQL_LISTAR.format(filtro=where), tuple(parametros) or None)


def listar(filtro="", estado="activos"):
    return [(f["uuid"], f["title"], f["publication_year"], f["type"], f["language"],
             f["category"]) for f in listar_detalle(filtro, estado)]


def obtener(uuid_texto):
    """Fila completa (claves = columnas de historico) + listas hijas, o None."""
    filas = consultar_dicts(_SQL_OBTENER, (u.obligatorio(uuid_texto, "El UUID"),))
    if not filas:
        return None
    d = filas[0]
    d["uuid"] = d.pop("uuid_texto")
    return d


def para_formulario(d):
    """Convierte lo obtenido en los textos que muestra el formulario."""
    return {
        "title": d["title"], "publication_year": d["publication_year"], "type": d["type"],
        "language": d["language"], "category": d["category"], "volumen": d["volumen"],
        "number_of_pages": d["number_of_pages"], "pages": d["pages"], "abstract": d["abstract"],
        "portal_url": d["portal_url"],
        "contributors": "\n".join(d["contributors"]),
        "identifiers": "; ".join(d["identifiers"]),
        "keywords_groups": "; ".join(d["keywords_groups"]),
    }


def _lista_como_texto(valor):
    if isinstance(valor, (list, tuple)):
        return "\n".join(str(item) for item in valor if item is not None)
    return valor


def _preparar_guardado(
    d, coordinador, uuid_existente=None, fecha_reporte=None, uuid_nuevo=None
):
    actual = obtener(uuid_existente) if uuid_existente else None
    if uuid_existente and actual is None:
        raise u.ErrorOperacion("La publicacion que intenta modificar ya no existe.")

    def previo(clave, defecto=None):
        return actual[clave] if actual and actual.get(clave) is not None else defecto

    hoy = date.today()
    titulo = u.obligatorio(d.get("title"), "El titulo")
    anio = u.entero(d.get("publication_year"), "El anio de publicacion")
    tipo = u.obligatorio(d.get("type"), "El tipo")
    contribuyentes = u.partir(_lista_como_texto(d.get("contributors")))
    if not contribuyentes:
        raise u.ErrorOperacion("Indique al menos un contribuyente (uno por linea).")
    identificador = uuid_existente or uuid_nuevo or str(_uuid.uuid4())
    if actual:
        fecha_rep = date(actual["anio_reporte"], actual["mes_reporte"], actual["dia_reporte"])
    else:
        fecha_rep = fecha_reporte or hoy

    v = {
        "uuid": identificador, "title": titulo, "publication_year": anio, "type": tipo,
        "volumen": u.entero_opcional(d.get("volumen"), "El volumen"),
        "create_date": previo(
            "create_date", u.fecha(d["create_date"], "La fecha de creación")
            if d.get("create_date") else hoy),
        "journal_number": previo("journal_number", u.texto_opcional(d.get("journal_number"))),
        "create_by": previo("create_by", u.texto_opcional(d.get("create_by")) or "app"),
        # version = hash SHA-1 (40 caracteres hexadecimales) del contenido
        "version": hashlib.sha1(f"{identificador}|{titulo}|{anio}|{hoy}".encode("utf-8")).hexdigest(),
        "number_of_pages": u.entero_opcional(d.get("number_of_pages"), "El total de paginas"),
        "modified_by": "app",
        "abstract": u.texto_opcional(d.get("abstract")),
        "total_contributors": len(contribuyentes),
        "peer_review": previo("peer_review", d.get("peer_review", True)),
        "pages": u.texto_opcional(d.get("pages")),
        "type_discriminator": previo(
            "type_discriminator",
            d.get("type_discriminator") or TIPOS_PUBLICACION.get(tipo, "ContributionToJournal")),
        "bibliographical_note": previo(
            "bibliographical_note", u.texto_opcional(d.get("bibliographical_note"))),
        "visibility": previo("visibility", d.get("visibility") or "FREE"),
        "modified_date": u.fecha(d["modified_date"], "La fecha de modificación")
        if d.get("modified_date") else hoy,
        "submission_year": previo("submission_year", d.get("submission_year") or anio),
        "system_name": previo("system_name", d.get("system_name") or "ResearchOutput"),
        "portal_url": u.obligatorio(d.get("portal_url"), "La URL del portal"),
        "sub_title": previo("sub_title", u.texto_opcional(d.get("sub_title"))),
        "language": u.obligatorio(d.get("language"), "El idioma"),
        "category": u.obligatorio(d.get("category"), "La categoria"),
        "coordinador": coordinador, "fecha_reporte": fecha_rep,
        "contributors": contribuyentes,
        "identifiers": u.partir(_lista_como_texto(d.get("identifiers"))),
        "electronic_versions": previo(
            "electronic_versions", d.get("electronic_versions") or []),
        "keywords_groups": u.partir(_lista_como_texto(d.get("keywords_groups"))),
        "publication_status": previo(
            "publication_status", d.get("publication_status") or ["Published"]),
        "links": Json(previo("links", d.get("links") or [])),
    }
    parametros = [v[k] for k in ORDEN]
    tipos = [None] * len(ORDEN)
    tipos[ORDEN.index("uuid")] = "uuid"
    for k in ARRAYS:
        tipos[ORDEN.index(k)] = "varchar[]"
    tipos[ORDEN.index("links")] = "jsonb"
    return identificador, parametros, tipos


def guardar(d, coordinador, uuid_existente=None, fecha_reporte=None):
    """Inserta una publicacion nueva o actualiza la existente (mismo UUID)."""
    identificador, parametros, tipos = _preparar_guardado(
        d, coordinador, uuid_existente=uuid_existente, fecha_reporte=fecha_reporte)
    ejecutar_procedimiento("sp_cargar_historico", parametros, tipos)
    return identificador


def parametros_importacion(d, coordinador, uuid_fuente):
    """Prepara el CALL de la publicación para usarlo dentro de otra transacción."""
    _identificador, parametros, tipos = _preparar_guardado(
        d, coordinador, uuid_nuevo=uuid_fuente)
    return parametros, tipos


def eliminar(uuid_texto, motivo=None):
    """Borrado logico: la publicacion queda inactiva con fecha y motivo de baja."""
    ejecutar_procedimiento("sp_eliminar_historico",
                           [u.obligatorio(uuid_texto, "El UUID"), u.texto_opcional(motivo)],
                           ["uuid", "varchar"])


def reactivar(uuid_texto):
    ejecutar_procedimiento("sp_reactivar_historico", [u.obligatorio(uuid_texto, "El UUID")], ["uuid"])
