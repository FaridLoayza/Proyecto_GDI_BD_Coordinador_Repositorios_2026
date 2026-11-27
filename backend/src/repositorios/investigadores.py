"""CRUD de investigadores. Insertar, modificar, dar de baja y reactivar se hacen con
procedimientos almacenados (sp_registrar/modificar/eliminar/reactivar_investigador);
aqui solo se preparan los datos. Eliminar es un borrado logico (activo = FALSE)."""
from ..db.conexion import consultar_procedimiento, ejecutar_procedimiento
from . import utilidades as u

def listar_detalle(filtro="", estado="activos"):
    """Diccionarios con los datos del directorio. estado: activos | bajas | todos."""
    return consultar_procedimiento("sp_listar_investigadores",
                                   [(filtro or "").strip(), u.estado_valido(estado)])


def listar(filtro="", estado="activos"):
    """Filas (codigo, nombre, escuela, correo, celular). filtro busca en nombre o codigo."""
    return [(f["codigo_ucsm"], f["nombre"], f["escuela_profesional"], f["correo_elec"],
             f["n_celular"]) for f in listar_detalle(filtro, estado)]


def opciones():
    """Pares (codigo, 'codigo - nombre') para elegir inventores en patentes."""
    return [(f[0], f"{f[0]} - {f[1]}") for f in listar()]


def escuelas():
    filas = consultar_procedimiento("sp_listar_escuelas_activas")
    return [f["escuela_profesional"] for f in filas]


def obtener(codigo):
    """Todos los datos de un investigador (claves iguales a las del formulario) o None."""
    filas = consultar_procedimiento("sp_obtener_investigador", [u.entero(codigo, "El código institucional")])
    if not filas:
        return None
    d = filas[0]
    d["intereses"] = ", ".join(d["intereses"])
    return d


def _datos_comunes(d):
    intereses = u.partir(d.get("intereses"), con_comas=True)
    if not intereses:
        raise u.ErrorOperacion("Debe indicar al menos un interés de investigación.")
    return dict(
        nombres=u.obligatorio(d.get("nombres"), "Los nombres"),
        ap_pat=u.obligatorio(d.get("apellido_paterno"), "El apellido paterno"),
        ap_mat=u.obligatorio(d.get("apellido_materno"), "El apellido materno"),
        genero=u.obligatorio(d.get("genero"), "El genero"),
        nacimiento=u.fecha(d.get("fecha_nacimiento"), "La fecha de nacimiento"),
        escuela=u.obligatorio(d.get("escuela"), "La escuela profesional"),
        celular=u.entero(d.get("celular"), "El celular"),
        correo=u.obligatorio(d.get("correo"), "El correo"),
        orcid=u.obligatorio(d.get("orcid"), "El ORCID"),
        scopus=u.entero_opcional(d.get("scopus_id"), "El Scopus ID"),
        link=u.obligatorio(d.get("link_cti"), "El enlace CTI Vitae"),
        resumen=u.obligatorio(d.get("resumen"), "El resumen academico"),
        foto=u.obligatorio(d.get("foto"), "La foto de perfil"),
        ods=list(d.get("ods") or []),
        intereses=intereses,
    )


def validar_datos(d):
    """Valida un formulario sin escribirlo en las tablas operativas."""
    _datos_comunes(d)
    dni = u.obligatorio(d.get("dni"), "El DNI")
    if len(dni) != 8 or not dni.isdigit():
        raise u.ErrorOperacion("El DNI debe tener exactamente 8 digitos.")
    codigo = u.entero(d.get("codigo_ucsm"), "El código institucional")
    if not 1000000000 <= codigo <= 9999999999:
        raise u.ErrorOperacion("El código institucional debe tener 10 digitos.")
    if not d.get("ods"):
        raise u.ErrorOperacion("Debe indicar al menos un ODS.")


def registrar(d, coordinador):
    c = _datos_comunes(d)
    parametros = [
        u.obligatorio(d.get("dni"), "El DNI"), c["nombres"], c["ap_pat"], c["ap_mat"],
        c["genero"], c["nacimiento"],
        u.entero(d.get("codigo_ucsm"), "El código institucional"), c["escuela"], c["celular"], c["correo"],
        c["orcid"], c["scopus"], c["link"], c["resumen"], c["foto"],
        coordinador, c["ods"], c["intereses"],
    ]
    ejecutar_procedimiento("sp_registrar_investigador", parametros,
                           [None] * 16 + ["varchar[]", "varchar[]"])


def modificar(codigo, d):
    c = _datos_comunes(d)
    parametros = [
        u.entero(codigo, "El código institucional"), c["nombres"], c["ap_pat"], c["ap_mat"],
        c["genero"], c["nacimiento"], c["escuela"], c["celular"], c["correo"],
        c["orcid"], c["scopus"], c["link"], c["resumen"], c["foto"],
        c["ods"], c["intereses"],
    ]
    ejecutar_procedimiento("sp_modificar_investigador", parametros,
                           [None] * 14 + ["varchar[]", "varchar[]"])


def eliminar(codigo, motivo=None):
    """Borrado logico: el investigador queda inactivo con fecha y motivo de baja."""
    ejecutar_procedimiento("sp_eliminar_investigador",
                           [u.entero(codigo, "El codigo institucional"), u.texto_opcional(motivo)],
                           [None, "varchar"])


def reactivar(codigo):
    ejecutar_procedimiento("sp_reactivar_investigador", [u.entero(codigo, "El codigo institucional")])
