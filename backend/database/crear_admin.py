"""Crea (o actualiza) la cuenta de administrador del portal.

Uso, desde la raíz del proyecto:
    python backend/database/crear_admin.py

Con el ejecutable de Windows:  GestorInvestigacion.exe --crear-admin

Pide correo, nombre y contraseña por consola (la contraseña no se muestra).
Si el correo ya existe, actualiza el nombre y la contraseña y reactiva la cuenta.
Requiere la tabla cuenta_usuario (rol administrador) creada por la instalación desde cero.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.src.repositorios.administracion import crear_admin_interactivo  # noqa: E402

if __name__ == "__main__":
    sys.exit(crear_admin_interactivo())
