# Login ORCID (OAuth) y Scopus opcional — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El ORCID de la postulación se obtiene de un login OAuth en ORCID (prueba de propiedad) y el Scopus ID pasa a ser opcional, autocompletado desde ORCID.

**Architecture:** OAuth 3-legged (`/authenticate`) manejado por FastAPI; el `state` y el resultado verificado viven en la sesión firmada existente (`cris_session`). El frontend React redirige a `/api/auth/orcid/login` y, al volver, consulta `/api/auth/orcid/status`.

**Tech Stack:** FastAPI + Starlette sessions, httpx, PostgreSQL 16, React (Vite), unittest.

**Spec:** `docs/superpowers/specs/2026-11-20-orcid-oauth-design.md`

## Global Constraints

- Entorno ORCID por configuración (`sandbox`/`production`), nunca fijo en código.
- `redirect_uri` de desarrollo: `http://127.0.0.1:8000/api/auth/orcid/callback`; `frontend_origin`: `http://127.0.0.1:5173`.
- Sin tablas nuevas; el estado OAuth vive en la sesión.
- No modificar `/api/coordinator/applications/{id}/orcid-check`.
- Mensajes al usuario en español.

## Review Focus

- `state` ausente, distinto o reutilizado en el callback → rechazar sin guardar ORCID.
- El usuario cancela en ORCID (`?error=access_denied`) → volver al formulario con aviso, sin 500.
- ORCID sin configurar → `/login` responde aviso claro, no redirige a una URL rota.
- `external-identifiers` sin Scopus o con formato inesperado → Scopus `None`, sin error.
- Registro/corrección con ORCID enviado por el cliente distinto al de la sesión → se usa el de la sesión.

---

### Task 1: Scopus opcional en la base

**Files:** Create `backend/database/migracion_scopus_opcional.sql`; Modify `backend/database/base_datos_repositorio.sql` (tablas `formato_investigador`, `solicitud_investigador`), `backend/src/db/conexion.py`, `backend/src/repositorios/investigadores.py:83`.

- [ ] `scopus_id BIGINT UNIQUE` / `scopus_id BIGINT` (sin `NOT NULL`); CHECK `scopus_id IS NULL OR scopus_id > 0`.
- [ ] Migración idempotente: `ALTER COLUMN scopus_id DROP NOT NULL`, `DROP CONSTRAINT IF EXISTS` + `ADD CONSTRAINT` de ambos CHECK, en una transacción.
- [ ] `scopus=u.entero_opcional(d.get("scopus_id"), "El Scopus ID")`; mensaje para `ck_solicitud_investigador_scopus`.

### Task 2: Cliente OAuth en `backend/api/orcid.py`

**Produces:**
- `configuracion_oauth() -> dict` con `client_id, client_secret, environment, redirect_uri, frontend_origin, authorize_url, token_url, api_base, configurado: bool` (env `ORCID_*` primero, luego `[orcid]` de `config.ini`).
- `url_autorizacion(state: str) -> str`
- `intercambiar_codigo(code: str) -> dict` → `{"orcid": str, "nombre": str | None}`; lanza `ErrorOrcid`.
- `buscar_scopus_id(orcid_id: str) -> int | None` (nunca lanza).

- [ ] Pruebas (`OrcidOAuthTests`): URL contiene `client_id`, `response_type=code`, `scope=/authenticate`, `redirect_uri`, `state`; canje devuelve el `orcid` del JSON del token; respuesta sin `orcid` válido → `ErrorOrcid`; `buscar_scopus_id` lee `external-identifier[].external-id-type == "Scopus Author ID"` (sin distinguir mayúsculas) y devuelve `int`; JSON sin Scopus o HTTP error → `None`.
- [ ] Implementar; `verificar` usa `configuracion_oauth()` para credenciales/endpoints.

### Task 3: Endpoints y uso de la sesión en `backend/api/app.py` + `schemas.py`

- [ ] `ApplicationBody.scopus_id: int | None = Field(default=None, gt=0)`; payload `str(...)` o `None`.
- [ ] `GET /api/auth/orcid/login?next=register|investigator` → 503 JSON si no configurado; guarda `orcid_oauth_state`, `orcid_oauth_next`; 307 a ORCID.
- [ ] `GET /api/auth/orcid/callback` → valida `state` con `hmac.compare_digest` y lo consume; guarda `orcid_verificado`, `orcid_nombre`, `orcid_scopus_id`; redirige a `{frontend_origin}/register?orcid=ok|error` (o `/investigator`).
- [ ] `GET /api/auth/orcid/status` → `{configurado, orcid, nombre, scopus_id}`; `POST /api/auth/orcid/disconnect` (CSRF) limpia las tres claves.
- [ ] Registro: sin `orcid_verificado` → 409; sobrescribe `orcid`/`scopus_id` desde la sesión. Corrección: si hay ORCID en sesión lo usa, si no conserva el guardado en la solicitud. Limpia claves ORCID tras guardar.
- [ ] Pruebas: registro sin ORCID en sesión → 409 sin llamar a `registrar`; callback con `state` incorrecto → no guarda ORCID; registro con ORCID en sesión envía el ORCID de la sesión aunque el cliente mande otro.

### Task 4: Frontend `OrcidConnectField`

- [ ] Componente que consulta `/api/auth/orcid/status`, muestra botón "Conectar con ORCID" o el ORCID conectado (+ "Cambiar"), y el Scopus autocompletado o "No encontrado en ORCID".
- [ ] Antes de redirigir guarda el formulario en `sessionStorage['cris_form_borrador']`; `ApplicationForm` lo restaura al montar y lo borra al enviar con éxito.
- [ ] Envío bloqueado sin ORCID conectado (solo en registro); `scopus_id` → `Number` o `null`.
- [ ] `npm run build` sin errores.

### Task 5: Documentación

- [ ] `config.ini.example` sección `[orcid]`; README: migración, configuración y prueba del flujo.
