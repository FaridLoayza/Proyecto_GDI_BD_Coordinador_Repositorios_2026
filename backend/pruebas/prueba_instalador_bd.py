"""Pruebas del preflight del instalador, sin conectarse a PostgreSQL."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from backend.database.instalar_bd import (
    ErrorInstalacion,
    validar_base_vacia,
    validar_esquema,
)


class InstaladorTests(unittest.TestCase):
    def test_base_vacia_es_destino_valido(self):
        validar_base_vacia("repositorios_ucsm", 0)

    def test_base_con_tablas_se_rechaza_sin_instalar(self):
        with self.assertRaisesRegex(ErrorInstalacion, "no modificó nada"):
            validar_base_vacia("repositorios_ucsm", 43)

    def test_esquema_completo_requiere_43_tablas_y_fuente_pure(self):
        validar_esquema(
            43,
            "CHECK ((fuente = ANY (ARRAY['scopus', 'orcid', 'manual', 'pure'])))",
        )

    def test_esquema_incompleto_o_sin_pure_se_rechaza(self):
        with self.assertRaisesRegex(ErrorInstalacion, "esperaban 43"):
            validar_esquema(27, "CHECK (fuente IN ('manual'))")
        with self.assertRaisesRegex(ErrorInstalacion, "fuente 'pure'"):
            validar_esquema(43, "CHECK (fuente IN ('manual'))")


if __name__ == "__main__":
    unittest.main(verbosity=2)
