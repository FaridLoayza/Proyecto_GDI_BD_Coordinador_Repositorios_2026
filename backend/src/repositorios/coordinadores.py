"""Coordinador de repositorios: inicio de sesion y resumen de la pagina de inicio."""
from ..db.conexion import ErrorOperacion, consultar_procedimiento
from ..seguridad import verificar

def autenticar(correo, clave, cfg=None):
    """Devuelve los datos del coordinador (sin la contrasenia) o lanza ErrorOperacion."""
    correo = (correo or "").strip()
    if not correo or not clave:
        raise ErrorOperacion("Ingrese su correo y su contrasenia.")
    filas = consultar_procedimiento("sp_login_coordinador", [correo], cfg=cfg)
    if not filas or not verificar(clave, filas[0]["contrasenia"]):
        raise ErrorOperacion("Correo o contrasenia incorrectos.")
    coord = filas[0]
    if coord["fecha_retiro"] is not None:
        raise ErrorOperacion("Este coordinador ya fue retirado y no puede ingresar.")
    del coord["contrasenia"]
    coord["nombre"] = (f"{coord['nombres']} {coord['apellido_paterno']} "
                       f"{coord['apellido_materno']}")
    return coord


def resumen(codigo_coordinador, cfg=None):
    """Conteos para las tarjetas de la pagina de inicio."""
    return consultar_procedimiento("sp_resumen_coordinador", [codigo_coordinador], cfg=cfg)[0]
