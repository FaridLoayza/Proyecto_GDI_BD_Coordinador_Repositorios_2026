"""Pruebas aisladas de la API FastAPI y del adaptador ORCID."""
import csv
import io
import json
import os
import sys
import unittest
from unittest.mock import patch

import httpx

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

with patch.dict(os.environ, {"PORTAL_SESSION_SECRET": "portal-test-secret-0123456789-abcdefghijk"}):
    from fastapi.testclient import TestClient

    from backend.api import orcid, pure_csv
    from backend.api.app import app
    from backend.src.db.conexion import ErrorOperacion
    from backend.src.repositorios import historico, publicaciones_candidatas


VALID_ORCID = "0000-0002-1825-0097"


class PortalApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.csrf = self.client.get("/api/auth/me").json()["csrf_token"]

    def post(self, path, body):
        return self.client.post(
            path,
            json=body,
            headers={"X-CSRF-Token": self.csrf},
        )

    def login_coordinator(self):
        coordinator = {
            "codigo_ucsm": 1234567890,
            "nombre": "Coordinador",
            "correo_electronico": "coord@example.test",
        }
        with patch("backend.api.app.coordinadores.autenticar", return_value=coordinator):
            login = self.post(
                "/api/auth/login",
                {"role": "coordinator", "email": "coord@example.test", "password": "test"},
            )
        if login.status_code == 200:
            self.csrf = login.json()["csrf_token"]
        return login

    def test_health_endpoint(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_researcher_route_requires_login(self):
        response = self.client.get("/api/researcher/application")
        self.assertEqual(response.status_code, 401)

    def test_post_without_csrf_is_rejected(self):
        response = self.client.post(
            "/api/auth/login",
            json={"role": "coordinator", "email": "coord@example.test", "password": "test"},
        )
        self.assertEqual(response.status_code, 403)

    def test_coordinator_login_cannot_access_researcher_routes(self):
        login = self.login_coordinator()
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["user"]["role"], "coordinator")
        forbidden = self.client.get("/api/researcher/application")
        self.assertEqual(forbidden.status_code, 403)

    def test_coordinator_dashboard_returns_repository_indicators(self):
        self.login_coordinator()
        indicators = {
            "investigadores": 4,
            "escuelas": 2,
            "publicaciones": 7,
            "patentes": 1,
            "ods_vinculados": 3,
            "ranking_ods": [("ODS 3: Salud y bienestar", 2)],
            "top_escuelas": [("Ingeniería", 3)],
        }
        with patch("backend.api.app.reportes.indicadores", return_value=indicators):
            response = self.client.get("/api/coordinator/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["publicaciones"], 7)
        self.assertEqual(response.json()["ranking_ods"][0][1], 2)

    def test_investigators_and_registered_patents_are_coordinator_read_only_sections(self):
        self.login_coordinator()
        with patch("backend.api.app.investigadores.listar", return_value=[
            (1234567890, "Ana Prueba", "Ingeniería", "ana@example.test", 987654321),
        ]), patch("backend.api.app.investigadores.obtener", return_value={
            "codigo_ucsm": 1234567890, "nombres": "Ana", "apellido_paterno": "Prueba",
            "apellido_materno": "Portal", "ods": [], "intereses": "",
        }):
            directory = self.client.get("/api/coordinator/investigators?search=Ana")
            profile = self.client.get("/api/coordinator/investigators/1234567890")
        self.assertEqual(directory.status_code, 200)
        self.assertEqual(directory.json()[0]["escuela"], "Ingeniería")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["nombres"], "Ana")
        self.assertEqual(self.client.post("/api/coordinator/investigators").status_code, 405)

        with patch("backend.api.app.patentes.listar", return_value=[
            ("PE-12345", "Patente de prueba", "2024-01-01", "Perú", "1234567890"),
        ]), patch("backend.api.app.patentes.obtener", return_value={
            "n_patente": "PE-12345", "titulo": "Patente de prueba", "inventores": [1234567890],
        }):
            patents = self.client.get("/api/coordinator/patent-registry")
            patent = self.client.get("/api/coordinator/patent-registry/PE-12345")
        self.assertEqual(patents.status_code, 200)
        self.assertEqual(patents.json()[0]["n_patente"], "PE-12345")
        self.assertEqual(patent.status_code, 200)
        self.assertEqual(patent.json()["titulo"], "Patente de prueba")
        self.assertEqual(self.client.post("/api/coordinator/patent-registry").status_code, 405)

    def test_report_queries_are_catalogued_and_report_generation_requires_csrf(self):
        self.login_coordinator()
        with patch("backend.api.app.reportes.catalogo", return_value=[(1, "Total", False)]), \
                patch("backend.api.app.reportes.ejecutar", return_value=("Total", ["total"], [(3,)])):
            catalog = self.client.get("/api/coordinator/reports/catalog")
            result = self.client.get("/api/coordinator/reports/queries/1")
            unknown = self.client.get("/api/coordinator/reports/queries/99")
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(result.json()["filas"], [[3]])
        self.assertEqual(unknown.status_code, 404)
        denied = self.client.post("/api/coordinator/reports/issued", json={"fecha": "2026-01-01"})
        self.assertEqual(denied.status_code, 403)

    def test_publication_catalog_is_read_only(self):
        self.login_coordinator()
        self.assertEqual(self.client.post("/api/coordinator/publications").status_code, 405)

    def test_pure_preview_does_not_import_and_commit_only_stages_candidates(self):
        self.login_coordinator()
        content = b"uuid,title,publication_year,data,synced_at\n"
        records = [{"id_fuente": "pure-uuid"}]
        summary = {
            "filas": 1, "validas": 1, "invalidas": 0, "uuid_repetidos": 0,
            "errores": [], "muestra": [],
        }
        imported = {
            "filas_validas": 1, "candidatas_creadas": 1, "ya_en_historico": 0,
            "ya_importadas": 0, "posibles_duplicados_doi": 0,
            "vinculos_pure_exactos": 0, "campos_opcionales_omitidos": 0,
            "candidatas_en_lote": 1,
            "lote_sha256": "a" * 64,
        }
        batch = {
            "lote_sha256": "a" * 64, "total": 1, "aptas": 0,
            "revision_manual": 0, "consolidadas": 1, "descartadas": 0,
            "campos_opcionales_omitidos": 0, "motivos_revision": [],
            "muestra_aptas": [],
            "muestra_revision": [],
        }
        automatic = {
            "lote_sha256": "a" * 64,
            "publicaciones_consolidadas": 1,
            "vinculos_aprobados": 1,
            "revision_manual": 0,
        }
        with patch("backend.api.app.pure_csv.parse_pure_csv", return_value=(records, summary)), \
                patch("backend.api.app.publicaciones_candidatas.importar_pure",
                      return_value=imported) as stage, \
                patch("backend.api.app.publicaciones_candidatas.aprobar_lote_pure",
                      return_value=automatic) as approve, \
                patch("backend.api.app.publicaciones_candidatas.resumen_lote_pure",
                      return_value=batch):
            preview = self.client.post(
                "/api/coordinator/publications/import/preview",
                files={"file": ("pure.csv", content, "text/csv")},
                headers={"X-CSRF-Token": self.csrf},
            )
            stage.assert_not_called()
            committed = self.client.post(
                "/api/coordinator/publications/import",
                files={"file": ("pure.csv", content, "text/csv")},
                headers={"X-CSRF-Token": self.csrf},
            )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["validas"], 1)
        self.assertEqual(committed.status_code, 200)
        self.assertEqual(committed.json()["candidatas_creadas"], 1)
        self.assertEqual(committed.json()["revision_lote"]["consolidadas"], 1)
        self.assertEqual(
            committed.json()["consolidacion_automatica"]["publicaciones_consolidadas"], 1)
        stage.assert_called_once_with(records, "pure.csv", 1234567890, content)
        approve.assert_called_once_with("a" * 64, 1234567890)

    def test_pure_bulk_approval_requires_valid_batch_and_coordinator(self):
        self.login_coordinator()
        with patch("backend.api.app.publicaciones_candidatas.aprobar_lote_pure",
                   return_value={
                       "lote_sha256": "a" * 64,
                       "publicaciones_consolidadas": 4,
                       "vinculos_aprobados": 5,
                       "revision_manual": 2,
                   }) as approve:
            response = self.post(
                "/api/coordinator/publications/import/bulk-approve",
                {"lote_sha256": "a" * 64},
            )
            invalid = self.post(
                "/api/coordinator/publications/import/bulk-approve",
                {"lote_sha256": "not-a-digest"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["publicaciones_consolidadas"], 4)
        self.assertEqual(invalid.status_code, 422)
        approve.assert_called_once_with("a" * 64, 1234567890)

    def test_pure_curation_accepts_source_terms_outside_old_catalogs(self):
        self.login_coordinator()
        body = {
            "title": "Publicación de prueba",
            "publication_year": 2025,
            "type": "Conference contribution",
            "language": "Undefined/Unknown",
            "category": "Research",
            "portal_url": "https://pure.example.test/output",
            "contributors": ["Ana Prueba"],
            "identifiers": [],
            "keywords_groups": [],
            "publication_status": ["Published"],
            "links": [{
                "pure_id": 321,
                "link_type": "Scopus",
                "url": "https://scopus.example.test/record",
                "description": "Scopus record",
            }],
            "abstract": None,
            "volumen": None,
            "number_of_pages": None,
            "journal_number": None,
            "bibliographical_note": None,
            "pages": None,
        }
        automatic = {
            "lote_sha256": "a" * 64,
            "publicaciones_consolidadas": 2,
            "vinculos_aprobados": 2,
            "revision_manual": 1,
        }
        with patch("backend.api.app.publicaciones_candidatas.guardar_curacion",
                   return_value="a" * 64) as save, \
                patch("backend.api.app.publicaciones_candidatas.aprobar_lote_pure",
                      return_value=automatic) as approve:
            response = self.client.put(
                "/api/coordinator/publications/candidates/1/curation",
                json=body,
                headers={"X-CSRF-Token": self.csrf},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(save.call_args.args[1]["type"], "Conference contribution")
        self.assertEqual(save.call_args.args[1]["links"][0]["pure_id"], 321)
        self.assertEqual(response.json()["consolidacion_automatica"], automatic)
        approve.assert_called_once_with("a" * 64, 1234567890)

    def test_pure_curation_rejects_links_over_catalog_url_limit(self):
        self.login_coordinator()
        body = {
            "title": "Publicación de prueba",
            "publication_year": 2025,
            "type": "Article",
            "language": "English",
            "category": "Research",
            "portal_url": "https://pure.example.test/output",
            "contributors": ["Ana Prueba"],
            "links": [{
                "pure_id": 321,
                "link_type": "Scopus",
                "url": f"https://example.test/{'x' * 260}",
            }],
        }
        with patch("backend.api.app.publicaciones_candidatas.guardar_curacion") as save:
            response = self.client.put(
                "/api/coordinator/publications/candidates/1/curation",
                json=body,
                headers={"X-CSRF-Token": self.csrf},
            )
        self.assertEqual(response.status_code, 422)
        save.assert_not_called()

    def test_candidate_discard_requires_and_records_a_reason(self):
        self.login_coordinator()
        with patch("backend.api.app.publicaciones_candidatas.descartar") as discard:
            denied = self.post(
                "/api/coordinator/publications/candidates/1/discard", {"motivo": "  "})
            accepted = self.post(
                "/api/coordinator/publications/candidates/1/discard",
                {"motivo": "Fuera del alcance"},
            )
        self.assertEqual(denied.status_code, 422)
        self.assertEqual(accepted.status_code, 200)
        discard.assert_called_once_with(1, 1234567890, "Fuera del alcance")

    def test_registration_rejects_invalid_orcid_checksum_before_database_write(self):
        application = {
            "dni": "12345678",
            "codigo_ucsm": 2099000001,
            "correo": "ana@example.test",
            "nombres": "Ana",
            "apellido_paterno": "Prueba",
            "apellido_materno": "Portal",
            "genero": "Femenino",
            "fecha_nacimiento": "1990-01-01",
            "escuela": "Ingeniería",
            "celular": "987654321",
            "orcid": "0000-0000-0000-0002",
            "scopus_id": 123456,
            "link_cti": "https://example.test/cti",
            "resumen": "Perfil de prueba",
            "foto": "ana.png",
            "ods": ["ODS 1: Fin de la pobreza"],
            "intereses": ["Investigación"],
        }
        with patch("backend.api.app.solicitudes_investigador.registrar") as register:
            response = self.post(
                "/api/researcher/register",
                {"application": application, "password": "secure-password-123"},
            )
        self.assertEqual(response.status_code, 422)
        register.assert_not_called()


class OrcidTests(unittest.TestCase):
    def setUp(self):
        orcid._TOKEN_CACHE.clear()

    def test_checksum_accepts_known_valid_orcid(self):
        self.assertTrue(orcid.checksum_valido(VALID_ORCID))
        self.assertFalse(orcid.checksum_valido("0000-0000-0000-0002"))

    def test_missing_credentials_do_not_call_orcid(self):
        with patch.dict(os.environ, {"ORCID_CLIENT_ID": "", "ORCID_CLIENT_SECRET": ""}), \
                patch("backend.api.orcid.httpx.post") as token_request:
            result = orcid.verificar(VALID_ORCID)
        self.assertEqual(result[0], "no_disponible")
        token_request.assert_not_called()

    def test_public_record_status_is_returned_without_fetching_full_profile(self):
        token = httpx.Response(
            200,
            json={"access_token": "test-token", "expires_in": 3600},
            request=httpx.Request("POST", "https://orcid.org/oauth/token"),
        )
        with patch.dict(os.environ, {
            "ORCID_CLIENT_ID": "test-client",
            "ORCID_CLIENT_SECRET": "test-secret",
            "ORCID_ENVIRONMENT": "production",
        }), patch("backend.api.orcid.httpx.post", return_value=token), \
                patch("backend.api.orcid.httpx.get", return_value=httpx.Response(
                    200,
                    request=httpx.Request("GET", "https://pub.orcid.org/record"),
                )) as record:
            result = orcid.verificar(VALID_ORCID)
        self.assertEqual(result[0], "confirmado")
        self.assertEqual(result[1], f"https://orcid.org/{VALID_ORCID}")
        self.assertEqual(record.call_args.args[0], f"https://pub.orcid.org/v3.0/{VALID_ORCID}/record")
        self.assertEqual(record.call_args.kwargs["headers"]["Accept"], "application/json")

    def test_orcid_not_found_is_not_reported_as_confirmed(self):
        token = httpx.Response(
            200,
            json={"access_token": "test-token", "expires_in": 3600},
            request=httpx.Request("POST", "https://orcid.org/oauth/token"),
        )
        with patch.dict(os.environ, {
            "ORCID_CLIENT_ID": "not-found-client",
            "ORCID_CLIENT_SECRET": "test-secret",
            "ORCID_ENVIRONMENT": "production",
        }), patch("backend.api.orcid.httpx.post", return_value=token), \
                patch("backend.api.orcid.httpx.get", return_value=httpx.Response(
                    404,
                    request=httpx.Request("GET", "https://pub.orcid.org/record"),
                )):
            result = orcid.verificar(VALID_ORCID)
        self.assertEqual(result[0], "no_confirmado")


class PureCsvTests(unittest.TestCase):
    def build_csv(self, rows, columns=None):
        columns = columns or ["uuid", "title", "publication_year", "data", "synced_at"]
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue().encode("utf-8")

    def row(self, source_id, metadata=None, **overrides):
        return {
            "uuid": source_id,
            "title": "Artículo de prueba",
            "publication_year": "2024",
            "data": json.dumps(metadata or {
                "uuid": source_id,
                "type": "Article",
                "language": {"term": {"en_US": "English"}},
                "category": {"term": {"en_US": "Research"}},
                "contributors": [{
                    "name": {"firstName": "Ana", "lastName": "Prueba"},
                    "person": {"uuid": "pure-person-uuid"},
                }],
                "electronicVersions": [{"doi": "https://doi.org/10.1234/Example"}],
            }),
            "synced_at": "2025-01-01",
            **overrides,
        }

    def test_valid_export_extracts_doi_and_exact_person_uuid(self):
        source_id = "00000000-0000-0000-0000-000000000001"
        records, summary = pure_csv.parse_pure_csv(
            self.build_csv([self.row(source_id)]))
        self.assertEqual(summary["validas"], 1)
        self.assertEqual(records[0]["doi_normalizado"], "10.1234/example")
        self.assertEqual(records[0]["pure_person_uuids"], ["pure-person-uuid"])

    def test_duplicate_uuid_and_invalid_json_are_reported(self):
        source_id = "00000000-0000-0000-0000-000000000001"
        other_id = "00000000-0000-0000-0000-000000000002"
        rows = [
            self.row(source_id),
            self.row(source_id),
            self.row(other_id, data="{invalid json"),
        ]
        records, summary = pure_csv.parse_pure_csv(self.build_csv(rows))
        self.assertEqual(len(records), 1)
        self.assertEqual(summary["uuid_repetidos"], 1)
        self.assertEqual(summary["invalidas"], 2)

    def test_duplicate_doi_is_reported_without_rejecting_rows(self):
        first_id = "00000000-0000-0000-0000-000000000001"
        second_id = "00000000-0000-0000-0000-000000000002"
        records, summary = pure_csv.parse_pure_csv(self.build_csv([
            self.row(first_id),
            self.row(second_id),
        ]))
        self.assertEqual(len(records), 2)
        self.assertEqual(summary["doi_repetidos"], 1)

    def test_export_requires_all_pure_columns(self):
        content = self.build_csv(
            [{"uuid": "x", "title": "x"}], columns=["uuid", "title"])
        with self.assertRaisesRegex(ValueError, "Faltan columnas requeridas"):
            pure_csv.parse_pure_csv(content)


class PublicationImportPreparationTests(unittest.TestCase):
    def test_exact_pure_person_match_requires_one_registered_researcher(self):
        matches = publicaciones_candidatas._investigadores_pure_exactos(
            ["pure-one", "pure-ambiguous", "pure-two", "pure-one"],
            {
                "pure-one": [1234567890],
                "pure-ambiguous": [1234567891, 1234567892],
                "pure-two": [1234567893],
            },
        )
        self.assertEqual(matches, [1234567890, 1234567893])

    def test_batch_eligibility_uses_only_exact_pending_author_links(self):
        source_uuid = "00000000-0000-0000-0000-000000000001"
        person_uuid = "pure-person-uuid"
        candidate = {
            "id": 7,
            "id_fuente": source_uuid,
            "titulo": "Publicación de prueba",
            "anio_publicacion": 2024,
            "tipo": "Article",
            "metadatos_origen": {"data": {
                "type": "Article",
                "language": "English",
                "category": "Research",
                "portalUrl": "https://pure.example.test/output",
                "contributors": [{
                    "name": {"firstName": "Ana", "lastName": "Prueba"},
                    "person": {"uuid": person_uuid},
                }],
            }, "curacion": {
                "type": "Article", "language": "English", "category": "Research",
                "portal_url": "https://pure.example.test/output",
                "contributors": ["Prueba, Ana"],
            }},
        }
        links = [
            {"codigo_ucsm": 1234567890, "estado_revision": "pendiente",
             "pure_person_id": person_uuid},
            {"codigo_ucsm": 1234567891, "estado_revision": "pendiente",
             "pure_person_id": "different-person"},
            {"codigo_ucsm": 1234567892, "estado_revision": "aceptada",
             "pure_person_id": person_uuid},
        ]
        result = publicaciones_candidatas._clasificar_candidatura_lote(candidate, links)
        self.assertEqual(result["vinculos_exactos"], [1234567890])
        self.assertEqual(result["motivos"], [])

    def test_batch_eligibility_blocks_repeated_doi(self):
        source_uuid = "00000000-0000-0000-0000-000000000001"
        candidate = {
            "id": 7,
            "id_fuente": source_uuid,
            "titulo": "Publicación de prueba",
            "anio_publicacion": 2024,
            "tipo": "Article",
            "metadatos_origen": {"data": {
                "type": "Article", "language": "English", "category": "Research",
                "portalUrl": "https://pure.example.test/output",
                "contributors": [{
                    "name": {"firstName": "Ana", "lastName": "Prueba"},
                    "person": {"uuid": "pure-person-uuid"},
                }],
            }, "curacion": {
                "type": "Article", "language": "English", "category": "Research",
                "portal_url": "https://pure.example.test/output",
                "contributors": ["Prueba, Ana"],
            }},
        }
        link = {"codigo_ucsm": 1234567890, "estado_revision": "pendiente",
                "pure_person_id": "pure-person-uuid"}
        result = publicaciones_candidatas._clasificar_candidatura_lote(
            candidate, [link], doi_duplicado=True)
        self.assertTrue(any("DOI coincide" in reason for reason in result["motivos"]))

    def test_safe_curation_omits_over_limit_optional_fields_and_keeps_source(self):
        original_abstract = "a" * 4001
        record = {
            "titulo": "Publicación de prueba",
            "anio_publicacion": 2024,
            "tipo": "Article",
            "metadatos_origen": {"data": {
                "type": "Article",
                "language": {"term": {"en_US": "English"}},
                "category": {"term": {"en_US": "Research"}},
                "portalUrl": "https://pure.example.test/output",
                "abstract": original_abstract,
                "journalNumber": "12345678901",
                "contributors": [{
                    "name": {"firstName": "Ana", "lastName": "Prueba"},
                    "person": {"uuid": "pure-person-uuid"},
                }],
                "electronicVersions": [],
                "links": [{
                    "pureId": 10, "url": "https://pure.example.test/" + "x" * 250,
                }],
            }},
        }
        curation, omitted, blockers = publicaciones_candidatas._curacion_automatica(record)
        self.assertIsNone(curation["abstract"])
        self.assertEqual(curation["journal_number"], "")
        self.assertEqual(curation["links"], [])
        self.assertEqual(record["metadatos_origen"]["data"]["abstract"], original_abstract)
        self.assertEqual(len(omitted), 4)
        self.assertEqual(blockers, [])

    def test_safe_curation_keeps_missing_required_portal_url_for_manual_review(self):
        record = {
            "titulo": "Publicación de prueba",
            "anio_publicacion": 2024,
            "tipo": "Article",
            "metadatos_origen": {"data": {
                "type": "Article",
                "language": "English",
                "category": "Research",
                "portalUrl": "https://pure.example.test/" + "x" * 250,
                "contributors": [{"name": {"firstName": "Ana", "lastName": "Prueba"}}],
            }},
        }
        _curation, _omitted, blockers = publicaciones_candidatas._curacion_automatica(record)
        self.assertTrue(any("URL del portal" in reason for reason in blockers))

    def test_safe_curation_marks_unknown_visibility_without_claiming_open_access(self):
        record = {
            "titulo": "Publicación de prueba",
            "anio_publicacion": 2024,
            "tipo": "Article",
            "metadatos_origen": {"data": {
                "type": "Article",
                "language": "English",
                "category": "Research",
                "portalUrl": "https://pure.example.test/output",
                "visibility": "V" * 60,
                "peerReview": "false",
                "modifiedDate": "fecha-desconocida",
                "submissionYear": 2024,
                "contributors": [{"name": {"firstName": "Ana", "lastName": "Prueba"}}],
            }},
        }
        curation, omitted, blockers = publicaciones_candidatas._curacion_automatica(record)
        self.assertEqual(curation["visibility"], "UNKNOWN")
        self.assertFalse(curation["peer_review"])
        self.assertIsNone(curation["modified_date"])
        self.assertEqual(blockers, [])
        self.assertEqual({item["campo"] for item in omitted}, {"visibility", "modified_date"})

    def test_import_parameters_keep_pure_uuid_and_unmapped_source_terms(self):
        source_id = "00000000-0000-0000-0000-000000000001"
        data = {
            "title": "Contribución de conferencia",
            "publication_year": 2024,
            "type": "Conference contribution",
            "type_discriminator": "ContributionToConferenceProceeding",
            "language": "Undefined/Unknown",
            "category": "Research",
            "portal_url": "https://pure.example.test/output",
            "contributors": ["Prueba, Ana"],
            "identifiers": [],
            "electronic_versions": ["10.1234/example"],
            "keywords_groups": [],
        }
        params, _types = historico.parametros_importacion(data, 1234567890, source_id)
        self.assertEqual(params[historico.ORDEN.index("uuid")], source_id)
        self.assertEqual(params[historico.ORDEN.index("type")], "Conference contribution")
        self.assertEqual(
            params[historico.ORDEN.index("type_discriminator")],
            "ContributionToConferenceProceeding",
        )
        self.assertEqual(params[historico.ORDEN.index("language")], "Undefined/Unknown")

    def test_non_numeric_pure_volume_requires_explicit_curator_clearing(self):
        source_id = "00000000-0000-0000-0000-000000000001"
        data = {
            "title": "Publicación con páginas en el volumen",
            "publication_year": 2024,
            "type": "Article",
            "language": "English",
            "category": "Research",
            "portal_url": "https://pure.example.test/output",
            "contributors": ["Prueba, Ana"],
            "volumen": "299-302",
        }
        with self.assertRaisesRegex(ErrorOperacion, "volumen debe ser un numero entero"):
            historico.parametros_importacion(data, 1234567890, source_id)
        data["volumen"] = None
        params, _types = historico.parametros_importacion(data, 1234567890, source_id)
        self.assertIsNone(params[historico.ORDEN.index("volumen")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
