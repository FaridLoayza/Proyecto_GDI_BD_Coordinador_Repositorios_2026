"""Acceso a solicitudes de patente del Sistema Gestor de Investigación."""
from ..db.conexion import consultar_procedimiento, ejecutar_procedimiento


def _normalizar(fila):
    fila["clasificacion_ocde"] = fila["clasificacion_ocde"] or []
    fila["revisiones"] = consultar_procedimiento("sp_revisiones_solicitud_patente", [fila["id"]])
    return fila


def _solicitudes(solicitud_id=None, solicitante=None):
    return [_normalizar(fila) for fila in consultar_procedimiento(
        "sp_listar_solicitudes_patente", [solicitud_id, solicitante], ["bigint", "bigint"])]


def listar():
    """Solicitudes pendientes de revision u observadas."""
    return _solicitudes()


def listar_de_investigador(codigo_ucsm):
    return _solicitudes(solicitante=int(codigo_ucsm))


def obtener(solicitud_id):
    filas = _solicitudes(solicitud_id=int(solicitud_id))
    return filas[0] if filas else None


def crear(solicitante, datos):
    ejecutar_procedimiento(
        "sp_crear_solicitud_patente",
        [
            int(solicitante), datos["n_patente"], datos["titulo"],
            datos["editorial"], datos["fecha_registro"], datos["cip"],
            datos["pais"], datos["inventores"], datos["campos_ocde"],
            datos["objetivos_ocde"],
        ],
        [None] * 7 + ["bigint[]", "varchar[]", "varchar[]"],
    )


def actualizar(solicitud_id, datos):
    ejecutar_procedimiento(
        "sp_actualizar_solicitud_patente",
        [
            int(solicitud_id), datos["n_patente"], datos["titulo"],
            datos["editorial"], datos["fecha_registro"], datos["cip"],
            datos["pais"], datos["inventores"], datos["campos_ocde"],
            datos["objetivos_ocde"],
        ],
        [None] * 7 + ["bigint[]", "varchar[]", "varchar[]"],
    )


def resolver(solicitud_id, coordinador, resultado, motivo=None):
    ejecutar_procedimiento(
        "sp_resolver_solicitud_patente",
        [int(solicitud_id), int(coordinador), resultado, motivo],
    )
