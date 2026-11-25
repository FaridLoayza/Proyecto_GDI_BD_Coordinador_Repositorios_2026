"""Pruebas aisladas del asistente de primer inicio y de config_local."""
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

with patch.dict(os.environ, {"PORTAL_SESSION_SECRET": "portal-test-secret-0123456789-abcdefghijk"}):
    from fastapi.testclient import TestClient

    from backend.api.app import app
    from backend.src import config_local

CONFIG_INSTALADOR = """; Generado por el instalador
[postgresql]
host = localhost
port = 5433
dbname = bd_coordinador_repositorios
user = postgres
password = aleatoria-inicial-123456
connect_timeout = 5

[portal]
; no borrar este comentario
configuracion_inicial = pendiente
"""


class ConfigLocalTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.ruta = os.path.join(self.dir, "config.ini")
        open(self.ruta, "w", encoding="utf-8").write(CONFIG_INSTALADOR)

    def test_updates_existing_key_and_keeps_comments(self):
        config_local.actualizar("postgresql", {"password": "nueva-clave-segura"}, self.ruta)
        texto = open(self.ruta, encoding="utf-8").read()
        self.assertIn("password = nueva-clave-segura", texto)
        self.assertIn("; no borrar este comentario", texto)
        self.assertIn("; Generado por el instalador", texto)

    def test_adds_missing_keys_and_sections(self):
        config_local.actualizar("portal", {"paso_orcid": "omitido"}, self.ruta)
        config_local.actualizar("orcid", {"client_id": "APP-1"}, self.ruta)
        parser = config_local.leer(self.ruta)
        self.assertEqual(parser.get("portal", "paso_orcid"), "omitido")
        self.assertEqual(parser.get("portal", "configuracion_inicial"), "pendiente")
        self.assertEqual(parser.get("orcid", "client_id"), "APP-1")

    def test_rejects_newlines_in_values(self):
        with self.assertRaises(ValueError):
            config_local.actualizar("orcid", {"client_id": "APP-1\n[postgresql]"}, self.ruta)

    def test_pending_only_when_installer_marked_it(self):
        self.assertTrue(config_local.configuracion_inicial_pendiente(self.ruta))
        config_local.actualizar("portal", {"configuracion_inicial": "completada"}, self.ruta)
        self.assertFalse(config_local.configuracion_inicial_pendiente(self.ruta))


class AsistenteApiTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        open(os.path.join(self.dir, "config.ini"), "w", encoding="utf-8").write(CONFIG_INSTALADOR)
        for destino in ("backend.src.config_local.carpeta_base", "backend.src.db.conexion.carpeta_base"):
            parche = patch(destino, return_value=self.dir)
            parche.start()
            self.addCleanup(parche.stop)
        self.client = TestClient(app, client=("127.0.0.1", 50000))
        self.csrf = self.client.get("/api/auth/me").json()["csrf_token"]

    def post(self, ruta, body, client=None):
        return (client or self.client).post(ruta, json=body, headers={"X-CSRF-Token": self.csrf})

    def config(self):
        return config_local.leer(os.path.join(self.dir, "config.ini"))

    def test_status_reports_pending(self):
        datos = self.client.get("/api/setup/status").json()
        self.assertTrue(datos["pendiente"])
        self.assertEqual(datos["redirect_uri_sugerida"], "http://127.0.0.1:8000/api/auth/orcid/callback")

    def test_remote_clients_are_rejected(self):
        remoto = TestClient(app, client=("192.168.1.20", 50000))
        csrf = remoto.get("/api/auth/me").json()["csrf_token"]
        r = remoto.post("/api/setup/orcid", json={"omitir": True}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(r.status_code, 403)

    def test_requires_csrf(self):
        r = self.client.post("/api/setup/orcid", json={"omitir": True})
        self.assertEqual(r.status_code, 403)

    def test_change_database_password_runs_alter_role_and_saves_config(self):
        conexion = MagicMock()
        with patch("backend.api.asistente.conectar", return_value=conexion) as conectar:
            r = self.post("/api/setup/database", {"nueva_clave": "MiClaveSegura2026", "confirmacion": "MiClaveSegura2026"})
        self.assertEqual(r.status_code, 200)
        cursor = conexion.cursor.return_value.__enter__.return_value
        self.assertEqual(cursor.execute.call_args.args, ("ALTER ROLE CURRENT_USER WITH PASSWORD %s", ("MiClaveSegura2026",)))
        self.assertEqual(conectar.call_args_list[-1].args[0]["password"], "MiClaveSegura2026")
        self.assertEqual(self.config().get("postgresql", "password"), "MiClaveSegura2026")
        self.assertEqual(self.config().get("portal", "paso_base_datos"), "hecho")

    def test_password_rules(self):
        with patch("backend.api.asistente.conectar") as conectar:
            corta = self.post("/api/setup/database", {"nueva_clave": "corta", "confirmacion": "corta"})
            distinta = self.post("/api/setup/database", {"nueva_clave": "MiClaveSegura2026", "confirmacion": "OtraClave2026xx"})
        self.assertEqual((corta.status_code, distinta.status_code), (422, 422))
        conectar.assert_not_called()

    def test_orcid_credentials_are_validated_and_saved(self):
        with patch("backend.api.asistente.orcid._access_token", return_value="token") as token:
            r = self.post("/api/setup/orcid", {"client_id": "APP-ABCD1234EFGH5678", "client_secret": "secreto-123456",
                                               "environment": "sandbox", "redirect_uri": "http://127.0.0.1:8000/api/auth/orcid/callback"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(token.call_args.args[2], "https://sandbox.orcid.org/oauth/token")
        self.assertEqual(self.config().get("orcid", "client_id"), "APP-ABCD1234EFGH5678")
        self.assertEqual(self.config().get("portal", "paso_orcid"), "hecho")

    def test_rejected_orcid_credentials_are_not_saved(self):
        with patch("backend.api.asistente.orcid._access_token", side_effect=RuntimeError("401")):
            r = self.post("/api/setup/orcid", {"client_id": "APP-ABCD1234EFGH5678", "client_secret": "secreto-123456"})
        self.assertEqual(r.status_code, 422)
        self.assertFalse(self.config().has_section("orcid"))
        mal_id = self.post("/api/setup/orcid", {"client_id": "XYZ", "client_secret": "secreto-123456"})
        self.assertIn("APP-", mal_id.json()["detail"])

    def test_finish_requires_both_steps_then_disables_assistant(self):
        self.assertEqual(self.post("/api/setup/finish", {}).status_code, 409)
        config_local.actualizar("portal", {"paso_base_datos": "hecho"})
        self.post("/api/setup/orcid", {"omitir": True})
        self.assertEqual(self.post("/api/setup/finish", {}).status_code, 200)
        self.assertFalse(self.client.get("/api/setup/status").json()["pendiente"])
        self.assertEqual(self.post("/api/setup/orcid", {"omitir": True}).status_code, 409)


if __name__ == "__main__":
    unittest.main(verbosity=2)
