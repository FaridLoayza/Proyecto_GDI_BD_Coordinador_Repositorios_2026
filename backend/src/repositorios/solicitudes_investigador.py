"""Acceso a las cuentas, postulaciones y revisiones del esquema CRIS."""
from psycopg2.extras import Json

from ..db.conexion import ErrorOperacion, consultar_procedimiento, ejecutar_procedimiento
from ..seguridad import generar_hash, verificar


def _adjuntar_historial(solicitud):
    solicitud_id = solicitud["id"]
    solicitud["verificaciones"] = consultar_procedimiento("sp_verificaciones_solicitud", [solicitud_id])
    solicitud["revisiones"] = consultar_procedimiento("sp_revisiones_solicitud", [solicitud_id])
    solicitud["datos"] = {
        "dni": solicitud["dni"],
        "codigo_ucsm": solicitud["codigo_ucsm"],
        "correo": solicitud["correo_elec"],
        "nombres": solicitud["nombres"],
        "apellido_paterno": solicitud["apellido_paterno"],
        "apellido_materno": solicitud["apellido_materno"],
        "genero": solicitud["genero"],
        "fecha_nacimiento": solicitud["fecha_nacimiento"].isoformat(),
        "escuela": solicitud["escuela_profesional"],
        "celular": solicitud["n_celular"],
        "orcid": solicitud["codigo_orcid"],
        "scopus_id": solicitud["scopus_id"],
        "link_cti": solicitud["link_cti_vitae"],
        "resumen": solicitud["resumen_academico"],
        "foto": solicitud["foto_referencia"],
        "ods": solicitud["ods"],
        "intereses": solicitud["intereses"],
    }
    return solicitud


def registrar(datos, clave):
    """Crea una cuenta y su primera versión de postulación dentro del procedimiento SQL."""
    if len(clave or "") < 12:
        raise ErrorOperacion("La contraseña debe tener al menos 12 caracteres.")
    correo = str(datos.get("correo", "")).strip().lower()
    payload = dict(datos)
    payload["correo"] = correo
    ejecutar_procedimiento(
        "sp_crear_solicitud_investigador",
        [payload["dni"], int(payload["codigo_ucsm"]), correo,
         generar_hash(clave), Json(payload)],
        [None, None, None, None, "jsonb"],
    )


def autenticar(correo, clave):
    correo = (correo or "").strip()
    if not correo or not clave:
        raise ErrorOperacion("Ingrese su correo y su contraseña.")
    filas = consultar_procedimiento("sp_login_investigador", [correo])
    if not filas or not verificar(clave, filas[0]["password_hash"]):
        raise ErrorOperacion("Correo o contraseña incorrectos.")
    cuenta = filas[0]
    if cuenta["estado_cuenta"] != "activa":
        raise ErrorOperacion("La cuenta está bloqueada. Contacte al coordinador.")
    del cuenta["password_hash"]
    del cuenta["estado_cuenta"]
    cuenta["role"] = "investigator"
    return cuenta


def _obtener(solicitud_id=None, cuenta_id=None):
    filas = consultar_procedimiento("sp_obtener_solicitud_investigador",
                                    [solicitud_id, cuenta_id], ["bigint", "bigint"])
    return _adjuntar_historial(filas[0]) if filas else None


def obtener(solicitud_id):
    return _obtener(solicitud_id=int(solicitud_id))


def obtener_por_cuenta(cuenta_id):
    """Ultima postulacion de la cuenta."""
    return _obtener(cuenta_id=int(cuenta_id))


def listar():
    return consultar_procedimiento("sp_listar_solicitudes_investigador")


def actualizar(solicitud, datos):
    payload = dict(datos)
    payload["correo"] = str(payload["correo"]).strip().lower()
    ejecutar_procedimiento(
        "sp_actualizar_solicitud_investigador",
        [solicitud["id"], payload["dni"], int(payload["codigo_ucsm"]),
         payload["correo"], Json(payload)],
        [None, None, None, None, "jsonb"],
    )


def observar(solicitud_id, coordinador, comentario):
    ejecutar_procedimiento(
        "sp_observar_solicitud_investigador",
        [int(solicitud_id), int(coordinador), (comentario or "").strip()],
    )


def resolver(solicitud_id, coordinador, resultado, motivo=None):
    ejecutar_procedimiento(
        "sp_resolver_solicitud_investigador",
        [int(solicitud_id), int(coordinador), resultado, motivo],
    )


def registrar_verificacion(solicitud_id, version, fuente, metodo, resultado,
                           coordinador=None, referencia=None, nota=None):
    ejecutar_procedimiento(
        "sp_registrar_verificacion_solicitud",
        [int(solicitud_id), int(version), fuente, metodo, resultado,
         coordinador, referencia, nota],
    )


def perfiles_pure_pendientes():
    return consultar_procedimiento("sp_listar_pure_pendientes")


def registrar_pure(codigo_ucsm, pure_person_id, coordinador):
    ejecutar_procedimiento(
        "sp_registrar_pure_manual",
        [int(codigo_ucsm), pure_person_id, int(coordinador)],
    )
