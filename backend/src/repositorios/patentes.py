"""CRUD de patentes con procedimientos (sp_registrar/modificar/eliminar/reactivar_patente).
Eliminar es un borrado logico (activo = FALSE)."""
from ..db.conexion import consultar_procedimiento, ejecutar_procedimiento
from . import utilidades as u

def listar_detalle(estado="activos"):
    """Diccionarios del catalogo de patentes. estado: activos | bajas | todos."""
    return consultar_procedimiento("sp_listar_patentes", [u.estado_valido(estado)])


def listar(estado="activos"):
    return [(f["n_patente"], f["titulo_patente"], f["fecha_registro"], f["pais"], f["inventores"])
            for f in listar_detalle(estado)]


def obtener(n_patente):
    filas = consultar_procedimiento("sp_obtener_patente", [u.obligatorio(n_patente, "El numero de patente")])
    if not filas:
        return None
    d = filas[0]
    d["ocde"] = "\n".join(f"{c} | {o}" for c, o in zip(d.pop("campos"), d.pop("objetivos")))
    return d


def _ocde(texto):
    """Cada linea: 'campo | objetivo'. Devuelve (campos, objetivos)."""
    campos, objetivos = [], []
    for linea in u.partir(texto):
        if "|" not in linea:
            raise u.ErrorOperacion(f"Linea OCDE invalida '{linea}': use 'campo | objetivo'.")
        campo, objetivo = (x.strip() for x in linea.split("|", 1))
        if not campo or not objetivo:
            raise u.ErrorOperacion(f"Linea OCDE incompleta: '{linea}'.")
        campos.append(campo)
        objetivos.append(objetivo)
    return campos, objetivos


def _inventores(d):
    return [u.entero(c, "El codigo del inventor") for c in (d.get("inventores") or [])]


def registrar(d, coordinador):
    campos, objetivos = _ocde(d.get("ocde"))
    parametros = [
        u.obligatorio(d.get("n_patente"), "El numero de patente"),
        u.obligatorio(d.get("titulo"), "El titulo"),
        u.obligatorio(d.get("editorial"), "La editorial"),
        u.fecha(d.get("fecha_registro"), "La fecha de registro"),
        u.obligatorio(d.get("cip"), "El CIP"),
        u.obligatorio(d.get("pais"), "El pais"),
        coordinador, _inventores(d), campos, objetivos,
    ]
    ejecutar_procedimiento("sp_registrar_patente", parametros,
                           [None] * 7 + ["bigint[]", "varchar[]", "varchar[]"])


def modificar(n_patente, d):
    campos, objetivos = _ocde(d.get("ocde"))
    parametros = [
        u.obligatorio(n_patente, "El numero de patente"),
        u.obligatorio(d.get("titulo"), "El titulo"),
        u.obligatorio(d.get("editorial"), "La editorial"),
        u.fecha(d.get("fecha_registro"), "La fecha de registro"),
        u.obligatorio(d.get("cip"), "El CIP"),
        u.obligatorio(d.get("pais"), "El pais"),
        _inventores(d), campos, objetivos,
    ]
    ejecutar_procedimiento("sp_modificar_patente", parametros,
                           [None] * 6 + ["bigint[]", "varchar[]", "varchar[]"])


def eliminar(n_patente, motivo=None):
    """Borrado logico: la patente queda inactiva con fecha y motivo de baja."""
    ejecutar_procedimiento("sp_eliminar_patente",
                           [u.obligatorio(n_patente, "El numero de patente"), u.texto_opcional(motivo)],
                           [None, "varchar"])


def reactivar(n_patente):
    ejecutar_procedimiento("sp_reactivar_patente", [u.obligatorio(n_patente, "El numero de patente")])