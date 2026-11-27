"""
Prueba de conexion por consola (evidencia para la entrega al 30 %).
Uso:  python backend/pruebas/prueba_conexion.py o py backend/pruebas/prueba_conexion.py
Devuelve codigo 0 si todo esta correcto y 1 si algo falla.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.db.conexion import ErrorConexion, ejecutar_consulta, leer_configuracion, probar_conexion

TABLAS_ESPERADAS = 42
INDICES_ESPERADOS = 21
TABLAS_CRIS = (
    "cuenta_usuario", "solicitud_investigador",
    "solicitud_investigador_ods", "solicitud_investigador_interes",
    "solicitud_investigador_version", "revision_solicitud",
    "verificacion_solicitud", "integracion_ejecucion",
    "publicacion_candidata", "publicacion_candidata_investigador",
    "investigador_historico", "solicitud_patente",
    "solicitud_patente_investigador", "solicitud_patente_ocde",
    "uso_suscripcion",
)
PROCEDIMIENTOS_CRIS = (
    "sp_crear_solicitud_investigador", "sp_actualizar_solicitud_investigador",
    "sp_observar_solicitud_investigador", "sp_resolver_solicitud_investigador",
    "sp_aprobar_solicitud_investigador", "sp_registrar_verificacion_solicitud",
    "sp_registrar_pure_manual", "sp_crear_solicitud_patente",
    "sp_actualizar_solicitud_patente", "sp_resolver_solicitud_patente",
)


def paso(ok, texto):
    print(("[OK]    " if ok else "[FALLO] ") + texto)
    return ok


def main():
    print("=== Prueba de conexion - Repositorios ===")
    try:
        cfg = leer_configuracion()
        paso(True, f"config.ini leido ({cfg['user']}@{cfg['host']}:{cfg['port']}/{cfg['dbname']})")
        info = probar_conexion(cfg)
    except ErrorConexion as e:
        paso(False, str(e))
        return 1

    resultados = [
        paso(True, f"Conexion establecida - {info['version']}"),
        paso(True, f"Base: {info['base']} | Usuario: {info['usuario']}"),
        paso(info["tablas"] == TABLAS_ESPERADAS,
             f"Tablas en el esquema public: {info['tablas']} (esperadas {TABLAS_ESPERADAS})"),
        paso(info["indices"] == INDICES_ESPERADOS,
             f"Indices secundarios idx_*: {info['indices']} (esperados {INDICES_ESPERADOS})"),
    ]

    # Consulta con JOIN y parametro: demuestra que el aplicativo consume la base.
    try:
        columnas, filas = ejecutar_consulta(
            "SELECT i.codigo_ucsm, p.apellido_paterno, p.nombres, i.escuela_profesional "
            "FROM investigador i JOIN persona p ON p.dni = i.dni "
            "WHERE i.escuela_profesional ILIKE %s ORDER BY p.apellido_paterno",
            ("%Ingenier%",), cfg)
    except Exception as e:
        resultados.append(paso(False, "Consulta con JOIN: " + str(e).splitlines()[0]))
    else:
        resultados.append(paso(len(filas) > 0, f"Consulta con JOIN: {len(filas)} fila(s)"))
        for f in filas:
            print("          ", dict(zip(columnas, f)))

    try:
        _, tablas_faltantes = ejecutar_consulta("""
            SELECT requerida.nombre
              FROM unnest(%s::text[]) AS requerida(nombre)
              LEFT JOIN information_schema.tables t
                ON t.table_schema = 'public'
               AND t.table_name = requerida.nombre
             WHERE t.table_name IS NULL
             ORDER BY requerida.nombre
        """, (list(TABLAS_CRIS),))
        _, procedimientos_faltantes = ejecutar_consulta("""
            SELECT requerida.nombre
              FROM unnest(%s::text[]) AS requerida(nombre)
              LEFT JOIN pg_proc p
                ON p.proname = requerida.nombre
               AND p.prokind = 'p'
               AND p.pronamespace = 'public'::regnamespace
             WHERE p.oid IS NULL
             ORDER BY requerida.nombre
        """, (list(PROCEDIMIENTOS_CRIS),))
        _, reglas_fuente = ejecutar_consulta("""
            SELECT pg_get_constraintdef(c.oid)
              FROM pg_constraint c
              JOIN pg_class t ON t.oid = c.conrelid
              JOIN pg_namespace n ON n.oid = t.relnamespace
             WHERE n.nspname = 'public'
               AND t.relname = 'publicacion_candidata'
               AND c.conname = 'ck_publicacion_candidata_fuente'
        """)
    except ErrorConexion as e:
        resultados.append(paso(False, "Objetos nuevos CRIS: " + str(e).splitlines()[0]))
    else:
        faltantes = [nombre for (nombre,) in tablas_faltantes]
        faltantes += [nombre for (nombre,) in procedimientos_faltantes]
        resultados.append(paso(
            not faltantes,
            "Tablas y procedimientos CRIS presentes"
            if not faltantes else "Faltan objetos CRIS: " + ", ".join(faltantes)
        ))
        fuente_pure = bool(
            reglas_fuente and "'pure'" in str(reglas_fuente[0][0]).lower())
        resultados.append(paso(
            fuente_pure,
            "La restricción de fuentes permite importar Pure"
            if fuente_pure else "La restricción de fuentes no permite Pure",
        ))

    print("RESULTADO:", "TODO CORRECTO" if all(resultados) else "HAY PRUEBAS FALLIDAS")
    return 0 if all(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
