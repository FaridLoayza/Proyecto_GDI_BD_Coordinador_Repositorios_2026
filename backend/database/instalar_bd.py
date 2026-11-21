"""Instala desde cero el esquema CRIS y los datos demostrativos.

Crea la base 'bd_coordinador_repositorios' si no existe y luego instala el esquema.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import psycopg2

from src.db.conexion import ErrorConexion, conectar, leer_configuracion

SCRIPT = os.path.join(os.path.dirname(__file__), "base_datos_repositorio.sql")
TABLAS_ESPERADAS = 43
NOMBRE_BASE = "bd_coordinador_repositorios"
BASE_ADMINISTRATIVA = "postgres"  # base que siempre existe; desde aqui se crea NOMBRE_BASE


class ErrorInstalacion(Exception):
    """Error legible al validar el destino o el esquema recién instalado."""


def crear_base_si_falta(cfg):
    """Crea NOMBRE_BASE si no existe. Se conecta a la base 'postgres' para hacerlo."""
    conn = conectar({**cfg, "dbname": BASE_ADMINISTRATIVA})
    try:
        conn.autocommit = True  # CREATE DATABASE no puede ir dentro de una transaccion
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (NOMBRE_BASE,)
            )
            if cursor.fetchone():
                print(f"[INFO] La base '{NOMBRE_BASE}' ya existe.")
                return
            cursor.execute(
                f'CREATE DATABASE "{NOMBRE_BASE}" '
                "WITH ENCODING 'UTF8' TEMPLATE template0"
            )
            print(f"[OK] Base '{NOMBRE_BASE}' creada.")
    finally:
        conn.close()


def validar_base_vacia(nombre, cantidad_tablas):
    if cantidad_tablas:
        raise ErrorInstalacion(
            f"La base '{nombre}' ya contiene {cantidad_tablas} tabla(s) en public. "
            "El instalador no modificó nada: cree una base vacía para instalar."
        )


def validar_esquema(cantidad_tablas, definicion_fuente):
    if cantidad_tablas != TABLAS_ESPERADAS:
        raise ErrorInstalacion(
            f"Se esperaban {TABLAS_ESPERADAS} tablas y se encontraron "
            f"{cantidad_tablas}. La instalación no está completa."
        )
    if not definicion_fuente or "'pure'" not in definicion_fuente.lower():
        raise ErrorInstalacion(
            "No se encontró la fuente 'pure' en "
            "ck_publicacion_candidata_fuente."
        )


def main():
    try:
        cfg = leer_configuracion()
        cfg["dbname"] = NOMBRE_BASE  # el instalador siempre usa esta base
        crear_base_si_falta(cfg)
        conn = conectar(cfg)
    except (ErrorConexion, psycopg2.Error) as error:
        print("[FALLO]", error)
        return 1

    try:
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            nombre_base = cursor.fetchone()[0]
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )
            validar_base_vacia(nombre_base, cursor.fetchone()[0])

        print(f"[INFO] Base destino vacía: {nombre_base}.")
        with open(SCRIPT, encoding="utf-8") as archivo, conn.cursor() as cursor:
            cursor.execute(archivo.read())

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )
            cantidad_tablas = cursor.fetchone()[0]
            cursor.execute(
                "SELECT pg_get_constraintdef(constraint_row.oid) "
                "FROM pg_constraint AS constraint_row "
                "JOIN pg_class AS relation "
                "ON relation.oid = constraint_row.conrelid "
                "JOIN pg_namespace AS namespace "
                "ON namespace.oid = relation.relnamespace "
                "WHERE namespace.nspname = 'public' "
                "AND relation.relname = 'publicacion_candidata' "
                "AND constraint_row.conname = 'ck_publicacion_candidata_fuente'"
            )
            fuente_row = cursor.fetchone()
        definicion_fuente = fuente_row[0] if fuente_row else None
        validar_esquema(cantidad_tablas, definicion_fuente)
        print(
            f"[OK] Instalación completa en '{nombre_base}': "
            f"{cantidad_tablas} tablas; fuente Pure habilitada."
        )
        return 0
    except (ErrorInstalacion, OSError, UnicodeError, psycopg2.Error) as error:
        print("[FALLO] No se pudo completar la instalación:", error)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
