"""Pruebas aisladas (sin base de datos) de la Tarea 2: COUNTER, SUSHI y API de uso."""
import json
import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

with patch.dict(os.environ, {"PORTAL_SESSION_SECRET": "portal-test-secret-0123456789-abcdefghijk"}):
    from fastapi.testclient import TestClient

    from backend.api import counter, sushi
    from backend.api.app import app

EJEMPLO = os.path.join(ROOT, "backend", "database", "ejemplos", "reporte_counter5_PR_2026_ejemplo.json")


def json_50(items):
    return json.dumps({"Report_Header": {"Report_ID": "PR", "Created_By": "Elsevier"}, "Report_Items": items}).encode()


class CounterParserTests(unittest.TestCase):
    def test_example_file_is_a_valid_counter_report(self):
        registros, resumen = counter.parse_counter(open(EJEMPLO, "rb").read(), "ejemplo.json")
        self.assertEqual(resumen["plataformas"], ["ClinicalKey", "Engineering Village", "ScienceDirect", "Scopus"])
        self.assertEqual((resumen["desde"], resumen["hasta"]), ("2026-01-01", "2026-10-01"))
        self.assertEqual(resumen["filas"], len(registros))

    def test_json_50_sums_data_types_of_the_same_platform_month_and_metric(self):
        perf = lambda n: [{"Period": {"Begin_Date": "2025-03-01"}, "Instance": [{"Metric_Type": "Total_Item_Requests", "Count": n}]}]
        registros, _ = counter.parse_counter(json_50([
            {"Platform": "ScienceDirect", "Data_Type": "Journal", "Performance": perf(100)},
            {"Platform": "ScienceDirect", "Data_Type": "Book", "Performance": perf(25)},
        ]))
        self.assertEqual(registros, [{"plataforma": "ScienceDirect", "periodo": "2025-03-01",
                                      "metrica": "Total_Item_Requests", "valor": 125}])

    def test_json_51_attribute_performance_is_read(self):
        contenido = json.dumps({"Report_Header": {}, "Report_Items": [{"Platform": "Scopus", "Attribute_Performance": [
            {"Data_Type": "Database", "Performance": {"Searches_Platform": {"2025-01": 40, "2025-02": 55}}}]}]}).encode()
        registros, resumen = counter.parse_counter(contenido, "r.json")
        self.assertEqual([r["valor"] for r in registros], [40, 55])
        self.assertEqual(resumen["metricas"], ["Searches_Platform"])

    def test_tabular_csv_with_counter_header_and_month_columns(self):
        csv_texto = (
            "Report_Name,Platform Master Report\nCreated_By,Elsevier\n\n"
            "Platform,Data_Type,Access_Method,Metric_Type,Reporting_Period_Total,Jan-2025,Feb-2025\n"
            "ScienceDirect,Journal,Regular,Total_Item_Requests,30,10,20\n"
            "ScienceDirect,Book,Regular,Total_Item_Requests,5,2,3\n"
        ).encode()
        registros, resumen = counter.parse_counter(csv_texto, "pr.csv")
        self.assertEqual([(r["periodo"], r["valor"]) for r in registros], [("2025-01-01", 12), ("2025-02-01", 23)])
        self.assertEqual(resumen["proveedor"], "Elsevier")

    def test_unknown_metrics_are_ignored_and_reported(self):
        perf = [{"Period": {"Begin_Date": "2025-01-01"}, "Instance": [
            {"Metric_Type": "Total_Item_Requests", "Count": 3}, {"Metric_Type": "Metrica_Inventada", "Count": 9}]}]
        registros, resumen = counter.parse_counter(json_50([{"Platform": "Scopus", "Performance": perf}]))
        self.assertEqual(len(registros), 1)
        self.assertEqual(resumen["metricas_ignoradas"], ["Metrica_Inventada"])

    def test_invalid_files_raise_clear_errors(self):
        for contenido, nombre, mensaje in [
            (b"", "x.json", "vacío"),
            (b"{no es json", "x.json", "JSON no es válido"),
            (b'{"a": 1}', "x.json", "Report_Items"),
            (b"col1,col2\n1,2\n", "x.csv", "Platform"),
            (json_50([]), "x.json", "No se encontraron datos"),
        ]:
            with self.assertRaisesRegex(ValueError, mensaje):
                counter.parse_counter(contenido, nombre)

    def test_negative_or_text_counts_are_skipped(self):
        perf = [{"Period": {"Begin_Date": "2025-01-01"}, "Instance": [{"Metric_Type": "Total_Item_Requests", "Count": -4}]},
                {"Period": {"Begin_Date": "2025-02-01"}, "Instance": [{"Metric_Type": "Total_Item_Requests", "Count": "abc"}]},
                {"Period": {"Begin_Date": "2025-03-01"}, "Instance": [{"Metric_Type": "Total_Item_Requests", "Count": "1,200"}]}]
        registros, _ = counter.parse_counter(json_50([{"Platform": "Scopus", "Performance": perf}]))
        self.assertEqual([(r["periodo"], r["valor"]) for r in registros], [("2025-03-01", 1200)])


class SushiTests(unittest.TestCase):
    def test_sushi_is_disabled_by_default(self):
        with patch.object(sushi, "carpeta_base", return_value=os.path.join(ROOT, "no-existe")), \
                patch.dict(os.environ, {"SUSHI_HABILITADO": ""}):
            self.assertFalse(sushi.configuracion()["listo"])
            with self.assertRaisesRegex(sushi.ErrorSushi, "no está activada"):
                sushi.descargar_pr("2025-01", "2025-12")

    def test_enabled_sushi_requests_platform_report(self):
        import httpx
        respuesta = httpx.Response(200, json={"Report_Header": {}, "Report_Items": []},
                                   request=httpx.Request("GET", "https://api.elsevier.com/sushi/reports/pr"))
        with patch.object(sushi, "carpeta_base", return_value=os.path.join(ROOT, "no-existe")), \
                patch.dict(os.environ, {"SUSHI_HABILITADO": "true", "SUSHI_CUSTOMER_ID": "C1", "SUSHI_API_KEY": "K"}), \
                patch("backend.api.sushi.httpx.get", return_value=respuesta) as get:
            sushi.descargar_pr("2025-01", "2025-12")
        self.assertTrue(get.call_args.args[0].endswith("/reports/pr"))
        self.assertEqual(get.call_args.kwargs["params"]["begin_date"], "2025-01")
        self.assertEqual(get.call_args.kwargs["headers"]["X-ELS-APIKey"], "K")


class UsoApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.csrf = self.client.get("/api/auth/me").json()["csrf_token"]

    def login(self):
        coord = {"codigo_ucsm": 1234567890, "nombre": "Coord", "correo_electronico": "c@example.test"}
        with patch("backend.api.app.coordinadores.autenticar", return_value=coord):
            r = self.client.post("/api/auth/login", json={"role": "coordinator", "email": "c@example.test", "password": "x"},
                                 headers={"X-CSRF-Token": self.csrf})
        self.csrf = r.json()["csrf_token"]

    def test_usage_routes_require_coordinator(self):
        self.assertEqual(self.client.get("/api/coordinator/usage").status_code, 401)
        self.assertEqual(self.client.get("/api/coordinator/repository/summary").status_code, 401)

    def test_preview_does_not_write_and_import_saves_with_coordinator(self):
        self.login()
        archivo = {"file": ("ejemplo.json", open(EJEMPLO, "rb").read(), "application/json")}
        with patch("backend.api.app.uso_suscripciones.importar") as importar:
            preview = self.client.post("/api/coordinator/usage/import/preview", files=archivo, headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["filas"], 160)
        importar.assert_not_called()
        with patch("backend.api.app.uso_suscripciones.importar", return_value={"ejecucion_id": 1, "creados": 160, "actualizados": 0}) as importar:
            hecho = self.client.post("/api/coordinator/usage/import", files=archivo, headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(hecho.json()["creados"], 160)
        self.assertEqual(importar.call_args.args[1:3], ("ejemplo.json", 1234567890))

    def test_wrong_extension_and_bad_filters_are_rejected(self):
        self.login()
        r = self.client.post("/api/coordinator/usage/import/preview", files={"file": ("x.pdf", b"x", "application/pdf")},
                             headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.client.get("/api/coordinator/usage?metrica=Inventada").status_code, 422)
        self.assertEqual(self.client.get("/api/coordinator/usage?desde=2025-13").status_code, 422)

    def test_usage_series_passes_filters(self):
        self.login()
        with patch("backend.api.app.uso_suscripciones.serie", return_value={"filas": []}) as serie:
            self.client.get("/api/coordinator/usage?metrica=Searches_Platform&plataforma=Scopus&plataforma=ScienceDirect&desde=2025-01&hasta=2025-06")
        args = serie.call_args.args
        self.assertEqual(args[0], "Searches_Platform")
        self.assertEqual(args[1], ["Scopus", "ScienceDirect"])
        self.assertEqual((args[2].isoformat(), args[3].isoformat()), ("2025-01-01", "2025-06-01"))

    def test_export_csv_has_header_and_rows(self):
        self.login()
        filas = [{"plataforma": "Scopus", "proveedor": "Elsevier", "periodo": "2025-01", "metrica": "Searches_Platform", "valor": 7}]
        with patch("backend.api.app.uso_suscripciones.tabla_exportable", return_value=filas):
            r = self.client.get("/api/coordinator/usage/export.csv")
        self.assertIn("text/csv", r.headers["content-type"])
        self.assertIn("Scopus,Elsevier,2025-01,Searches_Platform,7", r.text)

    def test_sushi_sync_disabled_returns_503(self):
        self.login()
        with patch("backend.api.app.sushi.descargar_pr", side_effect=sushi.ErrorSushi("no está activada")):
            r = self.client.post("/api/coordinator/usage/sushi-sync", json={"desde": "2025-01", "hasta": "2025-12"},
                                 headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main(verbosity=2)
