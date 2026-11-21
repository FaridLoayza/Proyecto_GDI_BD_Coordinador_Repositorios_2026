"""
Prueba los CRUD originales y los flujos CRIS de postulación, verificaciones,
curación de publicaciones y solicitudes de patente. Crea datos ficticios y los
borra al terminar.
Uso:  python backend/pruebas/prueba_crud.py
"""
from datetime import date

from psycopg2.extras import Json

from _comun import (COD, COORD, CRIS_COD, CRIS_CORREO, CRIS_DNI, CRIS_PAT,
                    CRIS_PUBLICACION_ID, CRIS_TITULO_HIS, D_HIS, D_INV, D_PAT, ODS, PAT,
                    TITULO_HIS, esperar_error, escalar, ejecutar_consulta,
                    ejecutar_sentencia, ejecutar_procedimiento, investigadores,
                    historico, limpiar, limpiar_cris, paso, patentes, probar, terminar)
from src.repositorios import solicitudes_investigador
from src.seguridad import generar_hash


def crud_investigador():
    print("\n--- Investigador ---")
    probar("Registrar investigador (sp_registrar_investigador)", investigadores.registrar, D_INV, COORD)
    f = investigadores.obtener(COD)
    paso(bool(f) and f["nombres"] == "Prueba" and f["ods"] == [ODS[8]],
         "Consultar: los datos guardados coinciden")
    esperar_error("Registrar al mismo investigador otra vez", investigadores.registrar, D_INV, COORD,
                  contiene="ya esta registrado")
    otro = {**D_INV, "dni": "99999903", "codigo_ucsm": 2099000003, "orcid": "0000-0009-9999-9993",
            "scopus_id": 9900000003, "link_cti": "https://ctivitae.concytec.gob.pe/x/99999903"}
    esperar_error("Registrar con celular invalido (CHECK)", investigadores.registrar,
                  {**otro, "celular": 123456789}, COORD, contiene="celular")
    esperar_error("Registrar sin intereses de investigacion (obligatorios)", investigadores.registrar,
                  {**otro, "intereses": ""}, COORD, contiene="interés")
    esperar_error("Registrar sin ODS (obligatorio)", investigadores.registrar,
                  {**otro, "ods": []}, COORD, contiene="ODS")
    esperar_error("Registrar con coordinador inexistente", investigadores.registrar, otro, 1099999999,
                  contiene="coordinador")
    esperar_error("Registrar con DNI no numerico", investigadores.registrar,
                  {**otro, "dni": "ABC12345"}, COORD, contiene="dni")
    paso(escalar("SELECT COUNT(*) FROM persona WHERE dni = '99999903'") == 0,
         "Un registro rechazado no deja datos a medias (rollback)")

    cambios = {**D_INV, "escuela": "Ingeniería Civil", "celular": 988111222,
               "ods": [ODS[3], ODS[11]], "intereses": "Pruebas, Calidad"}
    probar("Modificar investigador (sp_modificar_investigador)", investigadores.modificar, COD, cambios)
    f = investigadores.obtener(COD)
    paso(f["escuela"] == "Ingeniería Civil" and f["celular"] == 988111222
         and sorted(f["ods"]) == sorted([ODS[3], ODS[11]]) and "Calidad" in f["intereses"],
         "Consultar: los cambios quedaron guardados")
    esperar_error("Modificar un investigador inexistente", investigadores.modificar, 2099999999,
                  cambios, contiene="no existe")
    paso(any(fila[0] == COD for fila in investigadores.listar("Automatica")),
         "Listar con filtro encuentra al investigador")


def crud_patente():
    print("\n--- Patente ---")
    probar("Registrar patente (sp_registrar_patente)", patentes.registrar, D_PAT, COORD)
    f = patentes.obtener(PAT)
    paso(bool(f) and f["inventores"] == [COD] and "Ingeniería y tecnología" in f["ocde"],
         "Consultar: inventor y clasificacion OCDE guardados")
    esperar_error("Registrar con inventor inexistente", patentes.registrar,
                  {**D_PAT, "n_patente": "PE-9990002", "inventores": [2099999999]}, COORD,
                  contiene="inventores")
    esperar_error("Registrar sin inventores", patentes.registrar,
                  {**D_PAT, "n_patente": "PE-9990002", "inventores": []}, COORD,
                  contiene="al menos un inventor")
    esperar_error("Registrar con numero de patente invalido (CHECK)", patentes.registrar,
                  {**D_PAT, "n_patente": "ABC"}, COORD, contiene="formato PE-")
    esperar_error("Registrar la misma patente dos veces", patentes.registrar, D_PAT, COORD,
                  contiene="ya esta registrada")

    cambios = {**D_PAT, "titulo": "Patente de prueba (modificada)", "pais": "Chile",
               "ocde": "Ciencias naturales | Matematicas\nIngeniería y tecnología | Otros"}
    probar("Modificar patente (sp_modificar_patente)", patentes.modificar, PAT, cambios)
    f = patentes.obtener(PAT)
    paso(f["titulo"].endswith("(modificada)") and f["pais"] == "Chile" and f["ocde"].count("|") == 2,
         "Consultar: titulo, pais y 2 lineas OCDE actualizados")
    esperar_error("Modificar quitando todos los inventores", patentes.modificar, PAT,
                  {**cambios, "inventores": []}, contiene="al menos un inventor")
    esperar_error("Modificar una patente inexistente", patentes.modificar, "PE-9999999", cambios,
                  contiene="no existe")
    esperar_error("Eliminar una patente inexistente", patentes.eliminar, "PE-9999999",
                  contiene="no existe")
    probar("Eliminar patente (sp_eliminar_patente)", patentes.eliminar, PAT)
    paso(patentes.obtener(PAT) is None, "La patente ya no existe")


def crud_historico():
    print("\n--- Publicacion (historico) ---")
    ok, uid = probar("Cargar publicacion nueva (sp_cargar_historico)", historico.guardar, D_HIS, COORD,
                     fecha_reporte=date(2000, 1, 1))
    if not ok:
        return
    f = historico.obtener(uid)
    paso(bool(f) and f["title"] == TITULO_HIS and len(f["version"]) == 40
         and f["total_number_of_contributors"] == 1, "Consultar: datos y hash de version correctos")
    cambios = {**D_HIS, "title": TITULO_HIS + " (modificada)", "contributors": "Uno, Autor\nDos, Autor"}
    probar("Modificar publicacion (mismo UUID, sp_cargar_historico)", historico.guardar, cambios, COORD,
           uuid_existente=uid)
    f = historico.obtener(uid)
    paso(f["title"].endswith("(modificada)") and f["total_number_of_contributors"] == 2
         and len(f["contributors"]) == 2, "Consultar: titulo y 2 contribuyentes actualizados")
    paso(escalar("SELECT COUNT(*) FROM historico WHERE uuid = %s::uuid", (uid,)) == 1,
         "Modificar no duplica el registro")
    esperar_error("Cargar sin contribuyentes", historico.guardar, {**D_HIS, "contributors": ""}, COORD,
                  contiene="contribuyente", fecha_reporte=date(2000, 1, 1))
    esperar_error("Cargar con URL invalida (CHECK)", historico.guardar,
                  {**D_HIS, "portal_url": "ftp://x"}, COORD, contiene="URL", fecha_reporte=date(2000, 1, 1))
    probar("Eliminar publicacion (sp_eliminar_historico)", historico.eliminar, uid)
    paso(historico.obtener(uid) is None, "La publicacion ya no existe")
    esperar_error("Eliminar una publicacion inexistente", historico.eliminar, uid, contiene="no existe")


def eliminar_investigador():
    print("\n--- Investigador (baja) ---")
    esperar_error("Eliminar un investigador inexistente", investigadores.eliminar, 2099999999,
                  contiene="no existe")
    probar("Eliminar investigador (sp_eliminar_investigador)", investigadores.eliminar, COD)
    paso(investigadores.obtener(COD) is None, "El investigador ya no existe")
    paso(escalar("SELECT COUNT(*) FROM persona WHERE dni = '99999901'") == 0,
         "Tambien se elimino su registro de persona")


def flujo_postulacion_cris():
    print("\n--- CRIS: postulación, verificaciones y aprobación ---")
    datos = {
        **D_INV,
        "dni": CRIS_DNI,
        "codigo_ucsm": CRIS_COD,
        "correo": CRIS_CORREO,
        "orcid": "0000-0009-9999-9101",
        "scopus_id": 9900000101,
        "link_cti": "https://ctivitae.concytec.gob.pe/appCTIVitae/#/detallesCV/99999801",
        "foto": "cris-prueba.png",
        "ods": [ODS[8]],
        "intereses": ["Pruebas", "Automatizacion"],
    }
    clave_hash = generar_hash("Cr1sPrueba-2026!")
    ok, _ = probar(
        "Crear cuenta y solicitud CRIS normalizada",
        ejecutar_procedimiento,
        "sp_crear_solicitud_investigador",
        [CRIS_DNI, CRIS_COD, CRIS_CORREO, clave_hash, Json(datos)],
        [None, None, None, None, "jsonb"],
    )
    if not ok:
        return None

    solicitud_id = escalar(
        "SELECT s.id FROM solicitud_investigador s "
        "JOIN cuenta_investigador c ON c.id = s.cuenta_investigador_id "
        "WHERE c.codigo_ucsm = %s",
        (CRIS_COD,))
    paso(
        escalar("SELECT COUNT(*) FROM solicitud_investigador_version "
                "WHERE solicitud_id = %s AND numero_version = 1", (solicitud_id,)) == 1
        and escalar("SELECT COUNT(*) FROM solicitud_investigador_ods "
                    "WHERE solicitud_id = %s", (solicitud_id,)) == 1
        and escalar("SELECT COUNT(*) FROM solicitud_investigador_interes "
                    "WHERE solicitud_id = %s", (solicitud_id,)) == 2,
        "La postulación guarda versión, ODS e intereses en tablas separadas")
    cuenta = solicitudes_investigador.autenticar(CRIS_CORREO, "Cr1sPrueba-2026!")
    postulacion = solicitudes_investigador.obtener(solicitud_id)
    bandeja = solicitudes_investigador.listar()
    paso(
        cuenta["solicitud_id"] == solicitud_id
        and cuenta["estado"] == "pendiente_revision"
        and postulacion["version_actual"] == 1
        and any(item["id"] == solicitud_id for item in bandeja),
        "El investigador inicia sesión y coordinador ve la postulación en bandeja",
    )

    probar(
        "Registrar resultado API de ORCID para la versión 1",
        ejecutar_procedimiento,
        "sp_registrar_verificacion_solicitud",
        [solicitud_id, 1, "orcid", "api", "confirmado", None,
         "https://orcid.org/0000-0009-9999-9101", "Resultado simulado por la prueba"],
    )
    probar(
        "Registrar verificación manual del código UCSM",
        ejecutar_procedimiento,
        "sp_registrar_verificacion_solicitud",
        [solicitud_id, 1, "codigo_ucsm", "manual", "requiere_revision", COORD,
         None, "Prueba de formato y duplicados locales"],
    )
    esperar_error(
        "La API no se permite para fuentes distintas de ORCID/Scopus",
        ejecutar_procedimiento,
        "sp_registrar_verificacion_solicitud",
        [solicitud_id, 1, "renacyt", "api", "confirmado", None, None, None],
        contiene="Solo ORCID y Scopus",
    )
    paso(
        escalar("SELECT estado FROM solicitud_investigador WHERE id = %s",
                (solicitud_id,)) == "pendiente_revision",
        "Los resultados de verificación no aprueban automáticamente la solicitud")

    probar(
        "El coordinador observa la solicitud y deja motivo",
        ejecutar_procedimiento,
        "sp_observar_solicitud_investigador",
        [solicitud_id, COORD, "Corregir el resumen académico"],
    )
    paso(
        escalar("SELECT estado FROM solicitud_investigador WHERE id = %s",
                (solicitud_id,)) == "observada"
        and escalar("SELECT COUNT(*) FROM revision_solicitud "
                    "WHERE solicitud_id = %s AND resultado = 'observada' "
                    "AND version_id = (SELECT id FROM solicitud_investigador_version "
                    "WHERE solicitud_id = %s AND numero_version = 1)",
                    (solicitud_id, solicitud_id)) == 1,
        "La observación conserva el resultado y la versión evaluada")

    corregidos = {**datos, "escuela": "Ingeniería de Pruebas Corregida",
                  "intereses": ["Pruebas", "Calidad"]}
    probar(
        "El investigador corrige y reenvía la solicitud observada",
        ejecutar_procedimiento,
        "sp_actualizar_solicitud_investigador",
        [solicitud_id, CRIS_DNI, CRIS_COD, CRIS_CORREO, Json(corregidos)],
        [None, None, None, None, "jsonb"],
    )
    paso(
        escalar("SELECT estado FROM solicitud_investigador WHERE id = %s",
                (solicitud_id,)) == "pendiente_revision"
        and escalar("SELECT version_actual FROM solicitud_investigador WHERE id = %s",
                    (solicitud_id,)) == 2
        and escalar("SELECT COUNT(*) FROM solicitud_investigador_version "
                    "WHERE solicitud_id = %s", (solicitud_id,)) == 2
        and escalar("SELECT datos_snapshot ->> 'escuela' "
                    "FROM solicitud_investigador_version "
                    "WHERE solicitud_id = %s AND numero_version = 2",
                    (solicitud_id,)) == "Ingeniería de Pruebas Corregida",
        "El reenvío crea una segunda versión pendiente de revisión")
    probar(
        "Registrar resultado API de Scopus para la versión 2",
        ejecutar_procedimiento,
        "sp_registrar_verificacion_solicitud",
        [solicitud_id, 2, "scopus", "api", "confirmado", None,
         "https://www.scopus.com/authid/detail.uri?authorId=9900000101",
         "Resultado simulado por la prueba"],
    )
    paso(
        escalar("SELECT COUNT(*) FROM verificacion_solicitud "
                "WHERE solicitud_id = %s", (solicitud_id,)) == 3,
        "Se conservan verificaciones por fuente y versión")
    esperar_error(
        "No se puede rechazar una solicitud sin motivo",
        ejecutar_procedimiento,
        "sp_resolver_solicitud_investigador",
        [solicitud_id, COORD, "rechazada", None],
        contiene="motivo",
    )
    paso(
        escalar("SELECT estado FROM solicitud_investigador WHERE id = %s",
                (solicitud_id,)) == "pendiente_revision",
        "Un rechazo inválido no cambia el estado de la solicitud")
    probar(
        "El coordinador aprueba la solicitud corregida",
        ejecutar_procedimiento,
        "sp_aprobar_solicitud_investigador",
        [solicitud_id, COORD],
    )
    paso(
        escalar("SELECT COUNT(*) FROM investigador i "
                "JOIN cuenta_investigador c ON c.id = i.cuenta_investigador_id "
                "WHERE c.codigo_ucsm = %s", (CRIS_COD,)) == 1
        and escalar("SELECT estado FROM solicitud_investigador WHERE id = %s",
                    (solicitud_id,)) == "aprobada"
        and escalar("SELECT pure_estado FROM investigador WHERE codigo_ucsm = %s",
                    (CRIS_COD,)) == "pendiente_manual"
        and escalar("SELECT COUNT(*) FROM revision_solicitud "
                    "WHERE solicitud_id = %s AND resultado = 'aprobada' "
                    "AND version_id = (SELECT id FROM solicitud_investigador_version "
                    "WHERE solicitud_id = %s AND numero_version = 2)",
                    (solicitud_id, solicitud_id)) == 1,
        "La aprobación crea el perfil local, registra su versión y deja Pure pendiente")

    esperar_error(
        "No se registra Pure con identificador vacío",
        ejecutar_procedimiento,
        "sp_registrar_pure_manual",
        [CRIS_COD, " ", COORD],
        contiene="identificador",
    )
    probar(
        "El coordinador registra manualmente el identificador Pure",
        ejecutar_procedimiento,
        "sp_registrar_pure_manual",
        [CRIS_COD, "pure-person-test-99999801", COORD],
    )
    paso(
        escalar("SELECT COUNT(*) FROM investigador WHERE codigo_ucsm = %s "
                "AND pure_estado = 'registrado_manual' "
                "AND pure_person_id = 'pure-person-test-99999801' "
                "AND pure_registrado_por = %s AND pure_registrado_en IS NOT NULL",
                (CRIS_COD, COORD)) == 1,
        "El alta manual Pure registra ID, coordinador y fecha")
    return solicitud_id


def flujo_publicaciones_cris(solicitud_id):
    print("\n--- CRIS: ejecuciones y curación de publicaciones ---")
    ejecutar_sentencia(
        "INSERT INTO integracion_ejecucion "
        "(sistema, operacion, disparador, estado, solicitud_id, codigo_ucsm, "
        "iniciada_en, finalizada_en, registros_leidos) "
        "VALUES ('orcid', 'verificar_persona', 'manual', 'completada', %s, %s, "
        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)",
        (solicitud_id, CRIS_COD))
    paso(
        escalar("SELECT COUNT(*) FROM integracion_ejecucion "
                "WHERE solicitud_id = %s AND sistema = 'orcid' "
                "AND estado = 'completada' AND registros_leidos = 1",
                (solicitud_id,)) == 1,
        "La ejecución de integración conserva su resultado resumido")

    ok, uuid = probar(
        "Crear publicación de prueba para curación",
        historico.guardar,
        {**D_HIS, "title": CRIS_TITULO_HIS},
        COORD,
        fecha_reporte=date(2000, 1, 1),
    )
    if not ok:
        return

    ejecutar_sentencia(
        "INSERT INTO publicacion_candidata "
        "(fuente, id_fuente, doi_normalizado, titulo, anio_publicacion, tipo, metadatos_origen) "
        "VALUES ('manual', %s, '10.9999/prueba-cris', %s, 2025, 'Article', %s::jsonb)",
        (CRIS_PUBLICACION_ID, CRIS_TITULO_HIS, Json({"origen": "prueba"})))
    candidata_id = escalar(
        "SELECT id FROM publicacion_candidata "
        "WHERE fuente = 'manual' AND id_fuente = %s", (CRIS_PUBLICACION_ID,))
    esperar_error(
        "Una candidatura revisada requiere coordinador y fecha",
        ejecutar_sentencia,
        "INSERT INTO publicacion_candidata_investigador "
        "(publicacion_candidata_id, codigo_ucsm, estado_revision) "
        "VALUES (%s, %s, 'aceptada')",
        (candidata_id, CRIS_COD),
        contiene="ck_candidata_investigador_revision",
    )
    ejecutar_sentencia(
        "INSERT INTO publicacion_candidata_investigador "
        "(publicacion_candidata_id, codigo_ucsm) VALUES (%s, %s)",
        (candidata_id, CRIS_COD))
    ejecutar_sentencia(
        "UPDATE publicacion_candidata_investigador "
        "SET estado_revision = 'aceptada', revisado_por = %s, "
        "revisado_en = CURRENT_TIMESTAMP, motivo = 'Curación de prueba' "
        "WHERE publicacion_candidata_id = %s AND codigo_ucsm = %s",
        (COORD, candidata_id, CRIS_COD))
    ejecutar_sentencia(
        "INSERT INTO investigador_historico "
        "(codigo_ucsm, uuid, publicacion_candidata_id, codigo_ucsm_coordinador) "
        "VALUES (%s, %s, %s, %s)",
        (CRIS_COD, uuid, candidata_id, COORD))
    paso(
        escalar("SELECT COUNT(*) FROM investigador_historico "
                "WHERE codigo_ucsm = %s AND uuid = %s AND publicacion_candidata_id = %s",
                (CRIS_COD, uuid, candidata_id)) == 1
        and escalar("SELECT estado_revision FROM publicacion_candidata_investigador "
                    "WHERE publicacion_candidata_id = %s AND codigo_ucsm = %s",
                    (candidata_id, CRIS_COD)) == "aceptada",
        "La publicación aceptada queda vinculada al investigador y al histórico")


def flujo_solicitud_patente_cris():
    print("\n--- CRIS: solicitud y aprobación de patente ---")
    parametros = [
        CRIS_COD, CRIS_PAT, "Patente CRIS de prueba", "INDECOPI",
        date(2025, 1, 1), "A01B 1/00", "Perú", [CRIS_COD],
        ["Ingeniería y tecnología"], ["Producción y tecnología industrial"],
    ]
    tipos = [None] * 7 + ["bigint[]", "varchar[]", "varchar[]"]
    esperar_error(
        "Un perfil inexistente no puede solicitar patente",
        ejecutar_procedimiento,
        "sp_crear_solicitud_patente",
        [2099000999, "PE-9990102", *parametros[2:]],
        tipos,
        contiene="Solo un investigador",
    )
    ok, _ = probar(
        "Crear solicitud de patente con inventor y clasificación OCDE",
        ejecutar_procedimiento,
        "sp_crear_solicitud_patente",
        parametros,
        tipos,
    )
    if not ok:
        return

    solicitud_id = escalar(
        "SELECT id FROM solicitud_patente WHERE n_patente = %s", (CRIS_PAT,))
    esperar_error(
        "No se puede rechazar una solicitud de patente sin motivo",
        ejecutar_procedimiento,
        "sp_resolver_solicitud_patente",
        [solicitud_id, COORD, "rechazada", None],
        contiene="motivo",
    )
    probar(
        "El coordinador observa la solicitud de patente",
        ejecutar_procedimiento,
        "sp_resolver_solicitud_patente",
        [solicitud_id, COORD, "observada", "Completar la descripción"],
    )
    paso(
        escalar("SELECT COUNT(*) FROM patente WHERE n_patente = %s", (CRIS_PAT,)) == 0
        and escalar("SELECT estado FROM solicitud_patente WHERE id = %s",
                    (solicitud_id,)) == "observada",
        "La observación no crea todavía la patente definitiva")

    corregidos = [
        solicitud_id, CRIS_PAT, "Patente CRIS de prueba corregida", "INDECOPI",
        date(2025, 1, 1), "A01B 1/00", "Perú", [CRIS_COD],
        ["Ingeniería y tecnología"], ["Producción y tecnología industrial"],
    ]
    probar(
        "El solicitante corrige y reenvía la patente",
        ejecutar_procedimiento,
        "sp_actualizar_solicitud_patente",
        corregidos,
        [None] * 7 + ["bigint[]", "varchar[]", "varchar[]"],
    )
    paso(
        escalar("SELECT estado FROM solicitud_patente WHERE id = %s",
                (solicitud_id,)) == "pendiente_revision"
        and escalar("SELECT version_actual FROM solicitud_patente WHERE id = %s",
                    (solicitud_id,)) == 2,
        "La corrección reabre la solicitud como versión 2")
    probar(
        "La aprobación crea la patente y la enlaza con la solicitud",
        ejecutar_procedimiento,
        "sp_resolver_solicitud_patente",
        [solicitud_id, COORD, "aprobada", None],
    )
    paso(
        escalar("SELECT COUNT(*) FROM formato_patente "
                "WHERE n_patente = %s AND solicitud_patente_id = %s",
                (CRIS_PAT, solicitud_id)) == 1
        and escalar("SELECT COUNT(*) FROM revision_solicitud_patente "
                    "WHERE solicitud_patente_id = %s AND version_evaluada = 1 "
                    "AND resultado = 'observada'", (solicitud_id,)) == 1
        and escalar("SELECT COUNT(*) FROM revision_solicitud_patente "
                    "WHERE solicitud_patente_id = %s AND version_evaluada = 2 "
                    "AND resultado = 'aprobada'", (solicitud_id,)) == 1
        and escalar("SELECT estado FROM solicitud_patente WHERE id = %s",
                    (solicitud_id,)) == "aprobada",
        "Quedan registradas ambas revisiones y el vínculo de la patente aprobada")


def main():
    print("=== Prueba de CRUD con procedimientos almacenados ===")
    limpiar_cris()
    limpiar()
    try:
        crud_investigador()
        crud_patente()
        crud_historico()
        eliminar_investigador()
        solicitud_id = flujo_postulacion_cris()
        if solicitud_id is not None:
            flujo_publicaciones_cris(solicitud_id)
            flujo_solicitud_patente_cris()
    finally:
        limpiar_cris()
        limpiar()
    return terminar()


if __name__ == "__main__":
    import sys
    sys.exit(main())

