"""Cuenta de administrador y CRUD genérico sobre las tablas del portal.

Seguridad:
- Los nombres de tablas y columnas se toman SOLO del catálogo de PostgreSQL
  (esquema public); lo que envía el usuario se compara contra esa lista y se
  inserta con psycopg2.sql.Identifier, nunca concatenado.
- Los valores viajan como parámetros y se convierten con el tipo real de la
  columna (format_type del catálogo).
- Las restricciones, claves foráneas y triggers de la base siguen aplicando.
- Si config.ini tiene la sección [postgresql_admin], el CRUD se conecta con
  ese usuario (p. ej. el rol admin_cris); si no, con la conexión normal.
"""
import configparser
import datetime
import decimal
import json
import os
import re
import uuid

import psycopg2
from psycopg2 import sql

from ..db.conexion import (
    ErrorOperacion,
    _mensaje_operacion,
    carpeta_base,
    conectar,
    consultar_dicts,
    ejecutar_sentencia,
    leer_configuracion,
)
from ..seguridad import generar_hash, verificar

TAMANO_MAXIMO = 100
COLUMNAS_SENSIBLES = {"password_hash", "contrasenia"}
MASCARA = "********"


class NoEncontrado(ErrorOperacion):
    """Tabla o fila inexistente."""


# --- Cuenta de administrador -------------------------------------------------

_SQL_LOGIN = """
SELECT id, correo_elec, nombre, password_hash, activo
  FROM cuenta_administrador
 WHERE lower(correo_elec) = lower(btrim(%s))
"""


def autenticar(correo, clave, cfg=None):
    correo = (correo or "").strip()
    if not correo or not clave:
        raise ErrorOperacion("Ingrese su correo y su contraseña.")
    try:
        filas = consultar_dicts(_SQL_LOGIN, (correo,), cfg)
    except ErrorOperacion as exc:
        if "cuenta_administrador" in str(exc):
            raise ErrorOperacion(
                "La cuenta de administrador no está instalada. Ejecute "
                "migracion_cuenta_administrador.sql y crear_admin.py.") from exc
        raise
    if not filas or not verificar(clave, filas[0]["password_hash"]):
        raise ErrorOperacion("Correo o contraseña incorrectos.")
    admin = filas[0]
    if not admin["activo"]:
        raise ErrorOperacion("Esta cuenta de administrador está desactivada.")
    return {"id": admin["id"], "correo": admin["correo_elec"], "nombre": admin["nombre"]}


_SQL_GUARDAR_ADMIN = """
INSERT INTO cuenta_administrador (correo_elec, nombre, password_hash)
VALUES (lower(btrim(%s)), btrim(%s), %s)
ON CONFLICT (lower(correo_elec)) DO UPDATE
   SET nombre = EXCLUDED.nombre,
       password_hash = EXCLUDED.password_hash,
       activo = TRUE
"""


def validar_datos_admin(correo, nombre, clave, confirmacion):
    """Devuelve el mensaje de error o None si los datos son válidos."""
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", (correo or "").strip()):
        return "Ingrese un correo válido."
    if not (nombre or "").strip():
        return "Ingrese un nombre."
    if len(clave or "") < 12:
        return "La contraseña debe tener al menos 12 caracteres."
    if clave != confirmacion:
        return "Las contraseñas no coinciden."
    return None


def guardar_admin(correo, nombre, clave, cfg=None):
    """Crea la cuenta o, si el correo existe, actualiza nombre y contraseña y la reactiva."""
    ejecutar_sentencia(_SQL_GUARDAR_ADMIN, (correo, nombre, generar_hash(clave)), cfg)


def crear_admin_interactivo():
    """Pide los datos por consola. Lo usan crear_admin.py y PortalCRIS.exe --crear-admin."""
    import getpass
    print("Crear cuenta de administrador del Portal CRIS")
    correo = input("Correo: ").strip()
    nombre = input("Nombre: ").strip()
    clave = getpass.getpass("Contraseña (mínimo 12 caracteres): ")
    confirmacion = getpass.getpass("Confirmar contraseña: ")
    error = validar_datos_admin(correo, nombre, clave, confirmacion)
    if error:
        print("[FALLO]", error)
        return 1
    try:
        guardar_admin(correo, nombre, clave)
    except Exception as exc:  # error de la base, sin config.ini o sin conexión
        print("[FALLO]", exc)
        return 1
    print(f"[OK] Cuenta de administrador lista: {correo.lower()}. Ingrese en /login/admin.")
    return 0


# --- Conexión del CRUD ---------------------------------------------------------

def configuracion_crud():
    """Configuración de conexión del CRUD: [postgresql_admin] sobre [postgresql]."""
    cfg = dict(leer_configuracion())
    parser = configparser.ConfigParser()
    ruta = os.path.join(carpeta_base(), "config.ini")
    if os.path.isfile(ruta):
        parser.read(ruta, encoding="utf-8")
    if parser.has_section("postgresql_admin"):
        seccion = parser["postgresql_admin"]
        for clave in ("user", "password"):
            valor = seccion.get(clave, "").strip()
            if valor:
                cfg[clave] = valor
    return cfg


# --- Catálogo ------------------------------------------------------------------

_SQL_TABLAS = """
SELECT c.relname AS nombre, GREATEST(c.reltuples, 0)::BIGINT AS filas_estimadas
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind = 'r'
 ORDER BY c.relname
"""

_SQL_COLUMNAS = """
SELECT a.attname AS nombre,
       format_type(a.atttypid, a.atttypmod) AS tipo,
       NOT a.attnotnull AS nullable,
       pg_get_expr(d.adbin, d.adrelid) AS por_defecto,
       a.attidentity AS identidad,
       a.attgenerated AS generada,
       COALESCE(a.attnum = ANY (i.indkey), FALSE) AS clave_primaria
  FROM pg_attribute a
  JOIN pg_class c ON c.oid = a.attrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
  LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
  LEFT JOIN pg_index i ON i.indrelid = c.oid AND i.indisprimary
 WHERE n.nspname = 'public' AND c.relname = %s
   AND a.attnum > 0 AND NOT a.attisdropped
 ORDER BY a.attnum
"""


def listar_tablas(cfg=None):
    return consultar_dicts(_SQL_TABLAS, None, cfg)


def describir(tabla, cfg=None):
    """Columnas de la tabla (o NoEncontrado si no es una tabla de public)."""
    columnas = consultar_dicts(_SQL_COLUMNAS, (tabla,), cfg)
    if not columnas:
        raise NoEncontrado(f"No existe la tabla '{tabla}'.")
    for col in columnas:
        col["identidad"] = col["identidad"] or None
        col["generada"] = col["generada"] or None
        col["sensible"] = col["nombre"] in COLUMNAS_SENSIBLES
        # Columnas que nunca se escriben a mano: GENERATED ALWAYS y calculadas.
        col["solo_lectura"] = col["identidad"] == "a" or col["generada"] is not None
    clave = [c["nombre"] for c in columnas if c["clave_primaria"]]
    return {"tabla": tabla, "columnas": columnas, "clave_primaria": clave}


# --- Conversión de valores --------------------------------------------------

def _a_json(valor):
    if valor is None or isinstance(valor, (bool, int, float, str)):
        return valor
    if isinstance(valor, decimal.Decimal):
        return str(valor)
    if isinstance(valor, (datetime.date, datetime.datetime, datetime.time)):
        return valor.isoformat()
    if isinstance(valor, (datetime.timedelta, uuid.UUID)):
        return str(valor)
    if isinstance(valor, (bytes, memoryview)):
        return bytes(valor).hex()
    if isinstance(valor, (list, tuple)):
        return [_a_json(v) for v in valor]
    if isinstance(valor, dict):
        return {str(k): _a_json(v) for k, v in valor.items()}
    return str(valor)


def _fila_json(columnas, fila):
    resultado = {}
    for nombre, valor in zip(columnas, fila):
        if nombre in COLUMNAS_SENSIBLES and valor is not None:
            resultado[nombre] = MASCARA
        else:
            resultado[nombre] = _a_json(valor)
    return resultado


def _valor_para_columna(col, valor):
    if valor is None:
        return None
    if col["sensible"]:
        texto = str(valor)
        return texto if texto.startswith("pbkdf2_sha256$") else generar_hash(texto)
    if isinstance(valor, (dict, list)) and col["tipo"] in ("json", "jsonb"):
        return json.dumps(valor, ensure_ascii=False)
    if isinstance(valor, bool):
        return "true" if valor else "false"
    return str(valor)


def _marcador(col):
    # El tipo sale del catálogo (format_type), no del usuario.
    return sql.SQL("%s::" + col["tipo"])


def _columnas_por_nombre(desc):
    return {c["nombre"]: c for c in desc["columnas"]}


def _validar_clave(desc, clave):
    pk = desc["clave_primaria"]
    if not pk:
        raise ErrorOperacion("La tabla no tiene clave primaria; no se puede editar ni eliminar desde el panel.")
    if not isinstance(clave, dict) or set(clave) != set(pk):
        raise ErrorOperacion("Indique la clave primaria completa de la fila: " + ", ".join(pk) + ".")
    return pk


def _ejecutar(consulta, parametros, cfg, devolver=True):
    conn = conectar(cfg or configuracion_crud())
    try:
        with conn.cursor() as cur:
            cur.execute(consulta, parametros)
            columnas = [d[0] for d in cur.description] if cur.description else []
            filas = cur.fetchall() if devolver and cur.description else []
            afectadas = cur.rowcount
        conn.commit()
        return columnas, filas, afectadas
    except psycopg2.Error as exc:
        conn.rollback()
        raise ErrorOperacion(_mensaje_operacion(exc)) from exc
    finally:
        conn.close()


# --- CRUD ----------------------------------------------------------------------

def listar_filas(tabla, pagina=1, tamano=25, buscar=None, cfg=None):
    desc = describir(tabla, cfg)
    pagina = max(1, int(pagina))
    tamano = min(max(1, int(tamano)), TAMANO_MAXIMO)
    ident = sql.Identifier(tabla)
    filtro = sql.SQL("")
    parametros = []
    if buscar and buscar.strip():
        filtro = sql.SQL(" WHERE t::text ILIKE %s")
        parametros.append(f"%{buscar.strip()}%")
    orden = desc["clave_primaria"] or [desc["columnas"][0]["nombre"]]
    consulta = sql.SQL(
        "SELECT t.*, COUNT(*) OVER () AS __total FROM {tabla} AS t{filtro} "
        "ORDER BY {orden} LIMIT %s OFFSET %s"
    ).format(
        tabla=ident, filtro=filtro,
        orden=sql.SQL(", ").join(sql.Identifier("t", c) for c in orden),
    )
    columnas, filas, _ = _ejecutar(consulta, parametros + [tamano, (pagina - 1) * tamano], cfg)
    total = filas[0][-1] if filas else 0
    if not filas and pagina > 1:
        conteo = sql.SQL("SELECT COUNT(*) FROM {tabla} AS t{filtro}").format(tabla=ident, filtro=filtro)
        total = _ejecutar(conteo, parametros, cfg)[1][0][0]
    columnas = columnas[:-1]
    return {
        "tabla": tabla,
        "columnas": desc["columnas"],
        "clave_primaria": desc["clave_primaria"],
        "filas": [_fila_json(columnas, fila[:-1]) for fila in filas],
        "total": total,
        "pagina": pagina,
        "tamano": tamano,
    }


def crear(tabla, valores, cfg=None):
    desc = describir(tabla, cfg)
    cols = _columnas_por_nombre(desc)
    desconocidas = set(valores) - set(cols)
    if desconocidas:
        raise ErrorOperacion("Columnas desconocidas: " + ", ".join(sorted(desconocidas)) + ".")
    usar = [n for n, v in valores.items() if not cols[n]["solo_lectura"] and v is not None and v != ""]
    if usar:
        consulta = sql.SQL("INSERT INTO {tabla} ({cols}) VALUES ({vals}) RETURNING *").format(
            tabla=sql.Identifier(tabla),
            cols=sql.SQL(", ").join(sql.Identifier(n) for n in usar),
            vals=sql.SQL(", ").join(_marcador(cols[n]) for n in usar),
        )
        parametros = [_valor_para_columna(cols[n], valores[n]) for n in usar]
    else:
        consulta = sql.SQL("INSERT INTO {tabla} DEFAULT VALUES RETURNING *").format(tabla=sql.Identifier(tabla))
        parametros = []
    columnas, filas, _ = _ejecutar(consulta, parametros, cfg)
    return _fila_json(columnas, filas[0])


def actualizar(tabla, clave, valores, cfg=None):
    desc = describir(tabla, cfg)
    cols = _columnas_por_nombre(desc)
    pk = _validar_clave(desc, clave)
    desconocidas = set(valores) - set(cols)
    if desconocidas:
        raise ErrorOperacion("Columnas desconocidas: " + ", ".join(sorted(desconocidas)) + ".")
    # Una columna sensible enmascarada o vacía significa "no cambiar".
    usar = [
        n for n, v in valores.items()
        if not cols[n]["solo_lectura"]
        and not (cols[n]["sensible"] and (v in (None, "", MASCARA)))
    ]
    if not usar:
        raise ErrorOperacion("No hay cambios para guardar.")
    consulta = sql.SQL("UPDATE {tabla} SET {sets} WHERE {donde} RETURNING *").format(
        tabla=sql.Identifier(tabla),
        sets=sql.SQL(", ").join(
            sql.SQL("{} = ").format(sql.Identifier(n)) + _marcador(cols[n]) for n in usar),
        donde=sql.SQL(" AND ").join(
            sql.SQL("{} = ").format(sql.Identifier(n)) + _marcador(cols[n]) for n in pk),
    )
    parametros = ([_valor_para_columna(cols[n], None if valores[n] == "" else valores[n]) for n in usar]
                  + [_valor_para_columna(cols[n], clave[n]) for n in pk])
    columnas, filas, _ = _ejecutar(consulta, parametros, cfg)
    if not filas:
        raise NoEncontrado("La fila ya no existe; recargue la tabla.")
    return _fila_json(columnas, filas[0])


def eliminar(tabla, clave, cfg=None):
    desc = describir(tabla, cfg)
    cols = _columnas_por_nombre(desc)
    pk = _validar_clave(desc, clave)
    consulta = sql.SQL("DELETE FROM {tabla} WHERE {donde}").format(
        tabla=sql.Identifier(tabla),
        donde=sql.SQL(" AND ").join(
            sql.SQL("{} = ").format(sql.Identifier(n)) + _marcador(cols[n]) for n in pk),
    )
    _, _, afectadas = _ejecutar(consulta, [_valor_para_columna(cols[n], clave[n]) for n in pk], cfg, devolver=False)
    if not afectadas:
        raise NoEncontrado("La fila ya no existe; recargue la tabla.")
    return afectadas
