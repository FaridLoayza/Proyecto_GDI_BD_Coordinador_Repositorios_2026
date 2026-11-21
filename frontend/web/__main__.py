"""Compatibilidad: `python -m frontend.web` inicia el portal FastAPI actual."""
from backend.api.__main__ import ejecutar


if __name__ == "__main__":
    ejecutar()
