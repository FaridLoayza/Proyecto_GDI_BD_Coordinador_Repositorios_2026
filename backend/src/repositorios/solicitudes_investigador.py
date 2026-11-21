"""Acceso a las cuentas, postulaciones y revisiones del esquema CRIS."""
from psycopg2.extras import Json

from ..db.conexion import ErrorOperacion, consultar_dicts, ejecutar_procedimiento
from ..seguridad import generar_hash, verificar


_SQL_AUTENTICAR = """
SELECT c.id, c.dni, c.codigo_ucsm, c.correo_elec, c.password_hash,
       c.estado_cuenta, s.id AS solicitud_id, s.estado
FROM cuenta_investigador c
JOIN LATERAL (
    SELECT id, estado
      FROM solicitud_investigador
     WHERE cuenta_investigador_id = c.id
     ORDER BY creado_en DESC, id DESC
     LIMIT 1
) s ON TRUE
WHERE lower(c.correo_elec) = lower(%s)
"""

_SQL_SOLICITUD = """
SELECT s.id, s.cuenta_investigador_id, c.dni, c.codigo_ucsm, c.correo_elec,
       s.estado, s.nombres, s.apellido_paterno, s.apellido_materno, s.genero,
       s.fecha_nacimiento, s.escuela_profesional, s.n_celular,
       s.codigo_orcid, s.scopus_id, s.link_cti_vitae, s.resumen_academico,
       s.foto_referencia, s.version_actual, s.enviada_en, s.creado_en AS creada_en,
       COALESCE((
           SELECT array_agg(o.ods ORDER BY o.ods)
             FROM solicitud_investigador_ods o WHERE o.solicitud_id = s.id
       ), '{}') AS ods,
       COALESCE((
           SELECT array_agg(i.interes ORDER BY i.interes)
             FROM solicitud_investigador_interes i WHERE i.solicitud_id = s.id
       ), '{}') AS intereses,
       (
           SELECT r.motivo FROM revision_solicitud r
            WHERE r.solicitud_id = s.id
            ORDER BY r.resuelto_en DESC, r.id DESC LIMIT 1
       ) AS ultima_observacion
FROM solicitud_investigador s
JOIN cuenta_investigador c ON c.id = s.cuenta_investigador_id
"""


def _adjuntar_historial(solicitud):
    solicitud_id = solicitud["id"]
    solicitud["verificaciones"] = consultar_dicts("""
        SELECT v.fuente, v.metodo, v.resultado, v.verificado_por, v.verificado_en,
               v.referencia_evidencia, v.nota, sv.numero_version
          FROM verificacion_solicitud v
          JOIN solicitud_investigador_version sv ON sv.id = v.version_id
         WHERE v.solicitud_id = %s
         ORDER BY v.verificado_en, v.id
    """, (solicitud_id,))
    solicitud["revisiones"] = consultar_dicts("""
        SELECT r.resultado, r.motivo, r.resuelto_por, r.resuelto_en,
               v.numero_version
          FROM revision_solicitud r
          JOIN solicitud_investigador_version v
            ON v.id = r.version_id
         WHERE r.solicitud_id = %s
         ORDER BY r.resuelto_en, r.id
    """, (solicitud_id,))
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
    filas = consultar_dicts(_SQL_AUTENTICAR, (correo,))
    if not filas or not verificar(clave, filas[0]["password_hash"]):
        raise ErrorOperacion("Correo o contraseña incorrectos.")
    cuenta = filas[0]
    if cuenta["estado_cuenta"] != "activa":
        raise ErrorOperacion("La cuenta está bloqueada. Contacte al coordinador.")
    del cuenta["password_hash"]
    del cuenta["estado_cuenta"]
    cuenta["role"] = "investigator"
    return cuenta


def obtener(solicitud_id):
    filas = consultar_dicts(_SQL_SOLICITUD + " WHERE s.id = %s", (int(solicitud_id),))
    return _adjuntar_historial(filas[0]) if filas else None


def obtener_por_cuenta(cuenta_id):
    filas = consultar_dicts(
        _SQL_SOLICITUD
        + " WHERE s.cuenta_investigador_id = %s"
        + " ORDER BY s.creado_en DESC, s.id DESC LIMIT 1",
        (int(cuenta_id),),
    )
    return _adjuntar_historial(filas[0]) if filas else None


def listar():
    filas = consultar_dicts("""
        SELECT s.id, c.correo_elec, c.dni, c.codigo_ucsm, s.estado,
               s.enviada_en AS creada_en,
               s.nombres, s.apellido_paterno, s.apellido_materno, s.codigo_orcid,
               s.scopus_id, s.version_actual
          FROM solicitud_investigador s
          JOIN cuenta_investigador c ON c.id = s.cuenta_investigador_id
         WHERE s.estado IN ('pendiente_revision', 'observada')
         ORDER BY CASE s.estado WHEN 'pendiente_revision' THEN 0 ELSE 1 END,
                  s.enviada_en, s.id
    """)
    return filas


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
    return consultar_dicts("""
        SELECT i.codigo_ucsm, p.nombres, p.apellido_paterno, p.apellido_materno,
               i.correo_elec, i.pure_estado
          FROM investigador i
          JOIN persona p ON p.dni = i.dni
         WHERE i.pure_estado = 'pendiente_manual'
         ORDER BY p.apellido_paterno, p.nombres
    """)


def registrar_pure(codigo_ucsm, pure_person_id, coordinador):
    ejecutar_procedimiento(
        "sp_registrar_pure_manual",
        [int(codigo_ucsm), pure_person_id, int(coordinador)],
    )
