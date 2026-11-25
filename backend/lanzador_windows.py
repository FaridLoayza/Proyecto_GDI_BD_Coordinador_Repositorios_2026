"""Punto de entrada del ejecutable de Windows (GestorInvestigacion.exe).

Inicia el portal (FastAPI + frontend React ya compilado) y abre el navegador.
config.ini se lee de la misma carpeta donde está el .exe.
Opciones:
    --instalar-bd    crea la base bd_coordinador_repositorios con el esquema y datos de prueba.
    --crear-admin    crea o actualiza la cuenta de administrador del portal.
    --sin-pausa      no espera Enter al terminar (lo usa el instalador).

Si config.ini tiene la sección [docker] (instalación con el instalador), antes
de abrir el portal se asegura de que Docker Desktop y el contenedor de la base
de datos estén encendidos.

Generar el ejecutable (lo hace el workflow .github/workflows/release-windows.yml):
    pyinstaller --onefile --name GestorInvestigacion --paths . --collect-submodules uvicorn
                --add-data "frontend/portal/dist;frontend/portal/dist"
                --add-data "backend/database/base_datos_repositorio.sql;backend/database"
                backend/lanzador_windows.py
"""
import configparser
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

import uvicorn


def _pausar():
    if getattr(sys, "frozen", False) and "--sin-pausa" not in sys.argv[1:]:
        input("Presione Enter para cerrar...")


def _carpeta():
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()


def _docker_listo():
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _asegurar_docker():
    """Enciende Docker Desktop y el contenedor de la base si la instalación usa Docker."""
    parser = configparser.ConfigParser()
    parser.read(os.path.join(_carpeta(), "config.ini"), encoding="utf-8")
    if not parser.has_section("docker"):
        return
    compose = parser.get("docker", "compose", fallback=os.path.join(_carpeta(), "docker-compose.yml"))
    if not shutil.which("docker"):
        print("AVISO: Docker no está instalado; la base de datos no se puede iniciar.")
        return
    if not _docker_listo():
        print("Iniciando Docker Desktop…")
        for ruta in (os.path.expandvars(r"%ProgramFiles%\Docker\Docker\Docker Desktop.exe"),
                     os.path.expandvars(r"%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe")):
            if os.path.isfile(ruta):
                subprocess.Popen([ruta])
                break
        for _ in range(60):
            if _docker_listo():
                break
            time.sleep(3)
        else:
            print("AVISO: Docker Desktop no respondió. Ábralo manualmente y vuelva a abrir el Gestor.")
            return
    print("Encendiendo la base de datos…")
    subprocess.run(["docker", "compose", "-f", compose, "up", "-d"], cwd=os.path.dirname(compose),
                   capture_output=True, timeout=180)
    for _ in range(40):
        estado = subprocess.run(["docker", "inspect", "-f", "{{.State.Health.Status}}", "gestor-investigacion-db"],
                                capture_output=True, text=True, timeout=20)
        if estado.stdout.strip() == "healthy":
            return
        time.sleep(2)
    print("AVISO: la base de datos tarda en iniciar; si ve errores, espere un momento y recargue.")


def main():
    if "--instalar-bd" in sys.argv[1:]:
        from backend.database import instalar_bd
        print("Instalación de la base de datos del Gestor de Investigación (esquema + datos de prueba)")
        codigo = instalar_bd.main()
        _pausar()
        sys.exit(codigo)

    if "--crear-admin" in sys.argv[1:]:
        from backend.src.repositorios.administracion import crear_admin_interactivo
        codigo = crear_admin_interactivo()
        _pausar()
        sys.exit(codigo)

    host = os.getenv("PORTAL_HOST", "127.0.0.1")
    port = int(os.getenv("PORTAL_PORT", "8000"))
    carpeta = _carpeta()
    _asegurar_docker()
    if not os.path.isfile(os.path.join(carpeta, "config.ini")):
        print(f"AVISO: no se encontró config.ini en {carpeta}.")
        print("Copie config.ini.example como config.ini y complete los datos de PostgreSQL y ORCID.\n")

    # Importar aquí para que los avisos anteriores se vean aunque la app falle al cargar.
    from backend.api.app import app

    url = f"http://{host}:{port}"
    print(f"Gestor de Investigación en {url}  (cierre esta ventana para detenerlo)")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
