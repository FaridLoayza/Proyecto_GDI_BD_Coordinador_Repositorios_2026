"""Punto de entrada del ejecutable de Windows (PortalCRIS.exe).

Inicia el portal (FastAPI + frontend React ya compilado) y abre el navegador.
config.ini se lee de la misma carpeta donde está el .exe.

Generar el ejecutable (lo hace el workflow .github/workflows/release-windows.yml):
    pyinstaller --onefile --name PortalCRIS --paths . --collect-submodules uvicorn
                --add-data "frontend/portal/dist;frontend/portal/dist"
                backend/lanzador_windows.py
"""
import os
import sys
import threading
import webbrowser

import uvicorn


def main():
    host = os.getenv("PORTAL_HOST", "127.0.0.1")
    port = int(os.getenv("PORTAL_PORT", "8000"))
    carpeta = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()
    if not os.path.isfile(os.path.join(carpeta, "config.ini")):
        print(f"AVISO: no se encontró config.ini en {carpeta}.")
        print("Copie config.ini.example como config.ini y complete los datos de PostgreSQL y ORCID.\n")

    # Importar aquí para que los avisos anteriores se vean aunque la app falle al cargar.
    from backend.api.app import app

    url = f"http://{host}:{port}"
    print(f"Portal CRIS en {url}  (cierre esta ventana para detenerlo)")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
