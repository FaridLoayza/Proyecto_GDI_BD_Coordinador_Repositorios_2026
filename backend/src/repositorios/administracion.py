"""Cuenta de administrador y CRUD genérico sobre las tablas del portal.

Seguridad:
- Todo pasa por procedimientos (CALL): el catálogo de tablas y columnas
  (sp_admin_listar_tablas, sp_admin_describir_tabla), la lectura de filas
  (sp_admin_listar_filas, sp_admin_contar_filas) y la escritura. Lo que envía
  el usuario se compara contra el catálogo y la base escapa cada identificador
  con format('%I').
- Insertar, modificar y eliminar se hacen con los procedimientos
  sp_admin_insertar, sp_admin_actualizar y sp_admin_eliminar; los valores
  viajan en JSONB y la base los convierte al tipo real de cada columna.
- Las tablas con borrado lógico (activo + fecha_baja) se dan de baja.
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
from psycopg2.extras import Json

from ..db.conexion import (
    ErrorOperacion,
    _mensaje_operacion,
    carpeta_base,
    conectar,
    consultar_procedimiento,
    ejecutar_procedimiento,
    leer_configuracion,
)
from ..seguridad import generar_hash, verificar

TAMANO_MAXIMO = 100
COLUMNAS_SENSIBLES = {"password_hash", "contrasenia"}
MASCARA = "********"


class NoEncontrado(ErrorOperacion):
    """Tabla o fila inexistente."""


# --- Cuenta de administrador -------------------------------------------------

def autenticar(correo, clave, cfg=None):
    correo = (correo or "").strip()
    if not correo or not clave:
        raise ErrorOperacion("Ingrese su correo y su contraseña.")
    try:
        filas = consultar_procedimiento("sp_login_administrador", [correo], cfg=cfg)
    except ErrorOperacion as exc:
        if "cuenta_usuario" in str(exc):
            raise ErrorOperacion(
                "La cuenta de administrador no está instalada. Reinstale el esquema "
                "desde cero y luego ejecute crear_admin.py.") from exc
        raise
    if not filas or not verificar(clave, filas[0]["password_hash"]):
        raise ErrorOperacion("Correo o contraseña incorrectos.")
    admin = filas[0]
    if admin["estado_cuenta"] != "activa":
        raise ErrorOperacion("Esta cuenta de administrador está desactivada.")
    return {"id": admin["id"], "correo": admin["correo_elec"], "nombre": admin["nombre"]}


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
    ejecutar_procedimiento("sp_guardar_administrador", [correo, nombre, generar_hash(clave)], cfg=cfg)


def crear_admin_interactivo():
    """Pide los datos por consola. Lo usan crear_admin.py y GestorInvestigacion.exe --crear-admin."""
    import getpass
    print("Crear cuenta de administrador del Sistema Gestor de Investigación")
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

def listar_tablas(cfg=None):
    return consultar_procedimiento("sp_admin_listar_tablas", cfg=cfg)


def describir(tabla, cfg=None):
    """Columnas de la tabla (o NoEncontrado si no es una tabla de public)."""
    columnas = consultar_procedimiento("sp_admin_describir_tabla", [tabla], cfg=cfg)
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


def _columnas_por_nombre(desc):
    return {c["nombre"]: c for c in desc["columnas"]}


def _validar_clave(desc, clave):
    pk = desc["clave_primaria"]
    if not pk:
        raise ErrorOperacion("La tabla no tiene clave primaria; no se puede editar ni eliminar desde el panel.")
    if not isinstance(clave, dict) or set(clave) != set(pk):
        raise ErrorOperacion("Indique la clave primaria completa de la fila: " + ", ".join(pk) + ".")
    return pk


# --- CRUD ----------------------------------------------------------------------

def listar_filas(tabla, pagina=1, tamano=25, buscar=None, cfg=None):
    desc = describir(tabla, cfg)
    pagina = max(1, int(pagina))
    tamano = min(max(1, int(tamano)), TAMANO_MAXIMO)
    buscar = (buscar or "").strip() or None
    orden = desc["clave_primaria"] or [desc["columnas"][0]["nombre"]]
    cfg = cfg or configuracion_crud()
    filas = consultar_procedimiento(
        "sp_admin_listar_filas", [tabla, buscar, orden, tamano, (pagina - 1) * tamano],
        [None, "text", "text[]", None, None], cfg=cfg)
    total = filas[0]["total"] if filas else 0
    if not filas and pagina > 1:
        total = consultar_procedimiento("sp_admin_contar_filas", [tabla, buscar],
                                        [None, "text"], cfg=cfg)[0]["total"]
    nombres = [c["nombre"] for c in desc["columnas"]]
    return {
        "tabla": tabla,
        "columnas": desc["columnas"],
        "clave_primaria": desc["clave_primaria"],
        "filas": [_fila_json(nombres, [f["fila"].get(n) for n in nombres]) for f in filas],
        "total": total,
        "pagina": pagina,
        "tamano": tamano,
    }


def _valor_para_procedimiento(col, valor):
    """Valor que viaja dentro del JSONB hacia sp_admin_*: jsonb_populate_record lo
    convierte al tipo real de la columna."""
    if valor is None or valor == "":
        return None
    if col["tipo"] in ("json", "jsonb") and isinstance(valor, str):
        try:
            return json.loads(valor)
        except ValueError:
            raise ErrorOperacion(f"La columna {col['nombre']} debe contener JSON válido.") from None
    return _valor_para_columna(col, valor)


def _llamar(procedimiento, parametros, cfg):
    """CALL a un procedimiento sp_admin_* y devuelve su parámetro INOUT."""
    conn = conectar(cfg or configuracion_crud())
    try:
        with conn.cursor() as cur:
            marcas = ", ".join(["%s"] * len(parametros) + ["NULL"])
            cur.execute(f"CALL {procedimiento}({marcas})", parametros)
            resultado = cur.fetchone()[0]
        conn.commit()
        return resultado
    except psycopg2.Error as exc:
        conn.rollback()
        if exc.pgcode == "P0002":      # no_data_found
            raise NoEncontrado(_mensaje_operacion(exc)) from exc
        raise ErrorOperacion(_mensaje_operacion(exc)) from exc
    finally:
        conn.close()


def _fila_desde_json(desc, fila):
    nombres = [c["nombre"] for c in desc["columnas"]]
    return _fila_json(nombres, [(fila or {}).get(n) for n in nombres])


def _validar_columnas(cols, valores):
    desconocidas = set(valores) - set(cols)
    if desconocidas:
        raise ErrorOperacion("Columnas desconocidas: " + ", ".join(sorted(desconocidas)) + ".")


def crear(tabla, valores, cfg=None):
    """INSERT mediante el procedimiento sp_admin_insertar."""
    desc = describir(tabla, cfg)
    cols = _columnas_por_nombre(desc)
    _validar_columnas(cols, valores)
    datos = {n: _valor_para_procedimiento(cols[n], v) for n, v in valores.items()
             if not cols[n]["solo_lectura"] and v is not None and v != ""}
    fila = _llamar("sp_admin_insertar", [tabla, Json(datos)], cfg)
    return _fila_desde_json(desc, fila)


def actualizar(tabla, clave, valores, cfg=None):
    """UPDATE mediante el procedimiento sp_admin_actualizar."""
    desc = describir(tabla, cfg)
    cols = _columnas_por_nombre(desc)
    pk = _validar_clave(desc, clave)
    _validar_columnas(cols, valores)
    # Una columna sensible enmascarada o vacía significa "no cambiar".
    datos = {
        n: _valor_para_procedimiento(cols[n], v) for n, v in valores.items()
        if not cols[n]["solo_lectura"]
        and not (cols[n]["sensible"] and (v in (None, "", MASCARA)))
    }
    if not datos:
        raise ErrorOperacion("No hay cambios para guardar.")
    clave_json = {n: _valor_para_procedimiento(cols[n], clave[n]) for n in pk}
    fila = _llamar("sp_admin_actualizar", [tabla, Json(clave_json), Json(datos)], cfg)
    return _fila_desde_json(desc, fila)


def eliminar(tabla, clave, cfg=None):
    """DELETE (o baja lógica si la tabla la tiene) mediante sp_admin_eliminar."""
    desc = describir(tabla, cfg)
    cols = _columnas_por_nombre(desc)
    pk = _validar_clave(desc, clave)
    clave_json = {n: _valor_para_procedimiento(cols[n], clave[n]) for n in pk}
    return _llamar("sp_admin_eliminar", [tabla, Json(clave_json)], cfg)
