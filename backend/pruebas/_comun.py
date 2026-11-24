"""Utilidades compartidas por las pruebas: salida [OK]/[FALLO], datos de prueba y limpieza.
Las pruebas crean datos con codigos/DNI/ORCID ficticios (2099..., 99999...) y los borran al terminar."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.conexion import (ErrorConexion, ejecutar_consulta, ejecutar_procedimiento,
                             ejecutar_sentencia)  # noqa: E402
from src.repositorios import historico, investigadores, patentes  # noqa: E402
from src.repositorios.catalogos import ODS  # noqa: E402

COORD = 1000123498                      # unico coordinador: Javier Fernando Angulo Osorio
COD = 2099000001                        # investigador de prueba
DNI_INV = "99999901"
DNI_RET = "99999902"                    # persona del coordinador retirado de prueba
COD_RET = 1099000002
PAT = "PE-9990001"
TITULO_HIS = "Publicación de prueba automática"
CRIS_COD = 2099000101
CRIS_DNI = "99999801"
CRIS_CORREO = "cris.prueba.99999801@ucsm.edu.pe"
CRIS_PAT = "PE-9990101"
CRIS_PUBLICACION_ID = "prueba-cris-publicacion-99999801"
CRIS_TITULO_HIS = "Publicación candidata CRIS de prueba"

D_INV = dict(
    dni=DNI_INV, nombres="Prueba", apellido_paterno="Automatica", apellido_materno="Test",
    genero="Femenino", fecha_nacimiento="1990-01-15", codigo_ucsm=COD,
    escuela="Ingeniería de Pruebas", celular=999000001, correo="TEST.Prueba@UCSM.EDU.PE",
    orcid="0000-0009-9999-9991", scopus_id=9900000001,
    link_cti="https://ctivitae.concytec.gob.pe/appCTIVitae/#/detallesCV/99999901",
    foto="prueba.png", resumen="Registro creado por las pruebas automaticas.",
    ods=[ODS[8]], intereses="Pruebas, Automatizacion")

D_PAT = dict(
    n_patente=PAT, titulo="Patente de prueba automatica", editorial="INDECOPI",
    fecha_registro="2025-01-01", cip="A01B 1/00", pais="Perú", inventores=[COD],
    ocde="Ingeniería y tecnología | Producción y tecnología industrial")

D_HIS = dict(
    title=TITULO_HIS, publication_year=2025, type="Article", language="Spanish",
    category="Research", volumen="", number_of_pages="", pages="1-10",
    abstract="Resumen de prueba.", portal_url="https://repositorio.ucsm.edu.pe/handle/test/1",
    contributors="Automatica Test, Prueba", identifiers="", keywords_groups="Pruebas")

_fallos = 0


def paso(ok, texto):
    global _fallos
    print(("[OK]    " if ok else "[FALLO] ") + texto)
    if not ok:
        _fallos += 1
    return ok


def probar(texto, funcion, *args, **kwargs):
    """Espera que la operacion funcione. Devuelve (ok, resultado)."""
    try:
        resultado = funcion(*args, **kwargs)
    except ErrorConexion as e:
        paso(False, f"{texto} -> {e}")
        return False, None
    paso(True, texto)
    return True, resultado


def esperar_error(texto, funcion, *args, contiene=None, **kwargs):
    """Espera que la base RECHACE la operacion (y que el mensaje mencione 'contiene')."""
    try:
        funcion(*args, **kwargs)
    except ErrorConexion as e:
        ok = contiene is None or contiene.lower() in str(e).lower()
        return paso(ok, f"{texto} -> rechazado: {e}")
    return paso(False, f"{texto} -> debio ser rechazado y no lo fue")


def escalar(sql, parametros=None):
    return ejecutar_consulta(sql, parametros)[1][0][0]


def borrar_patente(n_patente):
    """Borrado FISICO para limpiar las pruebas (sp_eliminar_patente es logico).
    Dispara trg_patente_antes_borrar, que elimina el formato y sus hijos."""
    ejecutar_sentencia("DELETE FROM patente WHERE n_patente = %s", (n_patente,))


def borrar_investigador(codigo):
    """Borrado FISICO para limpiar las pruebas (sp_eliminar_investigador es logico).
    Dispara trg_investigador_antes_borrar, que elimina su formato."""
    ejecutar_sentencia("DELETE FROM investigador_historico WHERE codigo_ucsm = %s", (codigo,))
    ejecutar_sentencia("DELETE FROM investigador WHERE codigo_ucsm = %s", (codigo,))


def limpiar_cris():
    """Limpia las filas ficticias del flujo CRIS antes y después de sus pruebas."""
    if escalar("SELECT EXISTS (SELECT 1 FROM patente WHERE n_patente = %s)", (CRIS_PAT,)):
        borrar_patente(CRIS_PAT)

    ejecutar_sentencia(
        "DELETE FROM revision_solicitud_patente "
        "WHERE solicitud_patente_id IN (SELECT id FROM solicitud_patente WHERE n_patente = %s)",
        (CRIS_PAT,))
    ejecutar_sentencia(
        "DELETE FROM solicitud_patente_investigador "
        "WHERE solicitud_patente_id IN (SELECT id FROM solicitud_patente WHERE n_patente = %s)",
        (CRIS_PAT,))
    ejecutar_sentencia(
        "DELETE FROM solicitud_patente_ocde "
        "WHERE solicitud_patente_id IN (SELECT id FROM solicitud_patente WHERE n_patente = %s)",
        (CRIS_PAT,))
    ejecutar_sentencia("DELETE FROM solicitud_patente WHERE n_patente = %s", (CRIS_PAT,))

    ejecutar_sentencia(
        "DELETE FROM investigador_historico WHERE codigo_ucsm = %s",
        (CRIS_COD,))
    ejecutar_sentencia(
        "DELETE FROM publicacion_candidata_investigador WHERE codigo_ucsm = %s",
        (CRIS_COD,))
    ejecutar_sentencia(
        "DELETE FROM publicacion_candidata WHERE fuente = 'manual' AND id_fuente = %s",
        (CRIS_PUBLICACION_ID,))

    solicitud_ids = (
        "SELECT s.id FROM solicitud_investigador s "
        "JOIN cuenta_investigador c ON c.id = s.cuenta_investigador_id "
        "WHERE c.codigo_ucsm = %s"
    )
    ejecutar_sentencia(
        f"DELETE FROM integracion_ejecucion WHERE codigo_ucsm = %s "
        f"OR solicitud_id IN ({solicitud_ids})",
        (CRIS_COD, CRIS_COD))
    ejecutar_sentencia(
        f"DELETE FROM verificacion_solicitud WHERE solicitud_id IN ({solicitud_ids})",
        (CRIS_COD,))
    ejecutar_sentencia(
        f"DELETE FROM revision_solicitud WHERE solicitud_id IN ({solicitud_ids})",
        (CRIS_COD,))
    ejecutar_sentencia(
        f"DELETE FROM solicitud_investigador_version WHERE solicitud_id IN ({solicitud_ids})",
        (CRIS_COD,))
    ejecutar_sentencia(
        f"DELETE FROM solicitud_investigador_ods WHERE solicitud_id IN ({solicitud_ids})",
        (CRIS_COD,))
    ejecutar_sentencia(
        f"DELETE FROM solicitud_investigador_interes WHERE solicitud_id IN ({solicitud_ids})",
        (CRIS_COD,))
    ejecutar_sentencia(
        f"DELETE FROM solicitud_investigador WHERE cuenta_investigador_id IN "
        f"(SELECT id FROM cuenta_investigador WHERE codigo_ucsm = %s)",
        (CRIS_COD,))

    if escalar("SELECT EXISTS (SELECT 1 FROM investigador WHERE codigo_ucsm = %s)",
               (CRIS_COD,)):
        borrar_investigador(CRIS_COD)
    ejecutar_sentencia(
        "DELETE FROM cuenta_investigador WHERE codigo_ucsm = %s", (CRIS_COD,))
    ejecutar_sentencia("DELETE FROM persona WHERE dni = %s", (CRIS_DNI,))

    _, publicaciones = ejecutar_consulta(
        "SELECT uuid FROM historico WHERE title = %s", (CRIS_TITULO_HIS,))
    for (uuid,) in publicaciones:
        ejecutar_sentencia("DELETE FROM historico WHERE uuid = %s", (uuid,))


def limpiar():
    """Borra todo lo que crean las pruebas (tambien restos de una ejecucion anterior fallida)."""
    pasos = (
        lambda: borrar_patente(PAT),
        lambda: borrar_investigador(COD),
        lambda: ejecutar_sentencia("DELETE FROM historico WHERE title LIKE %s", (TITULO_HIS + "%",)),
        lambda: ejecutar_sentencia("DELETE FROM reporte WHERE dia = 1 AND mes = 1 AND anio = 2000"),
        lambda: ejecutar_sentencia("DELETE FROM coordinador_repositorios WHERE codigo_ucsm = %s", (COD_RET,)),
        lambda: ejecutar_sentencia("DELETE FROM persona WHERE dni IN (%s, %s)", (DNI_INV, DNI_RET)),
    )
    for ejecutar in pasos:
        try:
            ejecutar()
        except ErrorConexion:
            pass


def terminar():
    print("RESULTADO:", "TODO CORRECTO" if _fallos == 0 else f"HAY {_fallos} PRUEBA(S) FALLIDA(S)")
    return 0 if _fallos == 0 else 1
