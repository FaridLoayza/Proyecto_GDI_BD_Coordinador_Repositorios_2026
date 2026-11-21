"""Inicia el servidor API ASGI local."""
import os

import uvicorn


def ejecutar():
    uvicorn.run(
        "backend.api.app:app",
        host=os.getenv("PORTAL_HOST", "127.0.0.1"),
        port=int(os.getenv("PORTAL_PORT", "8000")),
    )


if __name__ == "__main__":
    ejecutar()
