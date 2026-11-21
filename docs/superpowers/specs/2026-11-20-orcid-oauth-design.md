# Diseño — Login ORCID (OAuth) y Scopus opcional en la postulación

**Fecha:** 2026-11-20 · **Contexto:** `handoff-sesion-orcid-oauth-y-roadmap.md`, sección 4.
**Para:** entrega del curso (hoy). Entorno ORCID: `sandbox.orcid.org` (app ya registrada).

## Por qué

Hoy el formulario acepta cualquier ORCID escrito a mano: basta copiar el de otra
persona para pasar la validación (solo se comprueba el dígito de control y que el
registro exista). Con el login OAuth de ORCID (scope `/authenticate`) el investigador
entra a orcid.org con su propia contraseña y ORCID nos devuelve el identificador de
quien autorizó: eso sí prueba que el ORCID le pertenece.

Scopus no tiene un "login con Scopus" para autores. Se toma el Scopus Author ID de
los identificadores externos públicos del ORCID ya verificado; si no aparece, queda
vacío y el coordinador usa el panel existente "Registrar verificación manual".

## Objetivos / no objetivos

- **Sí:** ORCID verificado por OAuth en el registro y en la corrección de una
  solicitud observada; Scopus opcional y autocompletado; configuración por
  `config.ini`/variables de entorno; pruebas automáticas actualizadas.
- **No:** Tarea 2 (SUSHI), visto bueno del director (v2), cambios al botón
  "Consultar API pública" del coordinador, tablas nuevas (el estado OAuth vive en la
  sesión del servidor).

## Enfoques considerados

- **A** Tarea 1 + Tarea 2 simulada. **B (elegida)** solo Tarea 1. **C** Tarea 1 +
  cliente SUSHI real. Se eligió B por el plazo de hoy: menos riesgo para la entrega;
  la Tarea 2 queda para después.

## Flujo

```
Formulario ──[Conectar con ORCID]──► /api/auth/orcid/login  (guarda state en sesión)
   ▲                                          │ redirige
   │                                          ▼
   │                         sandbox.orcid.org/oauth/authorize (login del investigador)
   │                                          │ ?code=...&state=...
   │                                          ▼
   └──── redirige a /register ◄── /api/auth/orcid/callback
         (o /investigator)        valida state, canjea code → ORCID real,
                                  busca Scopus en external-identifiers,
                                  guarda orcid_verificado / orcid_scopus_id en sesión
```

Antes de salir a ORCID, el frontend guarda lo ya escrito del formulario en
`sessionStorage` (sin contraseñas) y lo restaura al volver, para no perderlo.

## Cambios por archivo

| Archivo | Cambio |
|---|---|
| `backend/database/migracion_scopus_opcional.sql` | **Nuevo.** `ALTER TABLE` para que `scopus_id` acepte `NULL` en `formato_investigador` y `solicitud_investigador` (CHECK `scopus_id IS NULL OR scopus_id > 0`). Se ejecuta una vez sobre la base ya instalada. |
| `backend/database/base_datos_repositorio.sql` | Mismo cambio en el `CREATE TABLE` de ambas tablas, para instalaciones nuevas. Los procedimientos no cambian (ya toleran `NULL` vía JSONB). |
| `backend/config.ini.example` | Sección `[orcid]`: `client_id`, `client_secret`, `environment` (`sandbox`/`production`), `redirect_uri`, `frontend_origin`. |
| `backend/api/orcid.py` | Se mantienen `checksum_valido` y `verificar`. Nuevo: `configuracion_oauth()` (variables de entorno primero, luego `config.ini`; `verificar` también la usa), `url_autorizacion(state)`, `intercambiar_codigo(code)` → ORCID real, `buscar_scopus_id(orcid)` (lee `external-identifiers`, tipo "Scopus Author ID"). |
| `backend/api/schemas.py` | `scopus_id: int \| None = None`; el payload envía `None` si no hay valor. |
| `backend/api/app.py` | Endpoints `GET /api/auth/orcid/login`, `GET /api/auth/orcid/callback`, `GET /api/auth/orcid/status`, `POST /api/auth/orcid/disconnect`. Registro y corrección **ignoran** el ORCID/Scopus del JSON y usan los de la sesión; registro sin ORCID verificado → 409. |
| `backend/src/repositorios/investigadores.py` | `entero_opcional` para Scopus en el alta manual del coordinador. |
| `backend/src/db/conexion.py` | Mensaje del CHECK de Scopus en ambas tablas. |
| `frontend/portal/src/App.jsx` | Componente `OrcidConnectField` en lugar del campo ORCID de texto; Scopus de solo lectura (autocompletado u "no encontrado"); no deja enviar sin ORCID conectado; guardado/restauración del formulario en `sessionStorage`. |
| `frontend/portal/vite.config.js` | Sin cambios: ya usa `127.0.0.1`, el mismo host de la URI registrada, así la cookie de sesión es la misma al volver de ORCID. |
| `backend/pruebas/prueba_portal_web.py` | Ajuste de la prueba de registro y pruebas nuevas: `state` inválido rechazado, canje de código y búsqueda de Scopus con `httpx` simulado, registro sin ORCID en sesión → 409. |
| `README.md` y `project_context/README.md` | Cómo configurar `[orcid]`, ejecutar la migración y probar el flujo. |

## Decisiones mías (revisa si no estás de acuerdo)

1. **Corrección de una solicitud observada:** si el investigador no vuelve a
   conectar ORCID, se conserva el ORCID/Scopus ya guardado en su solicitud (se
   verificó al registrarse). Si conecta de nuevo, se usa el nuevo. Así no se le
   obliga a repetir el login para corregir, por ejemplo, el celular.
2. **Scopus no se escribe a mano:** solo se autocompleta desde ORCID (como dice el
   handoff). Si no aparece, el coordinador lo verifica manualmente.
3. **`redirect_uri` en desarrollo:** `http://127.0.0.1:8000/api/auth/orcid/callback`
   (la registrada en sandbox.orcid.org, confirmada por la autora) y
   `frontend_origin = http://127.0.0.1:5173`. El navegador debe abrir siempre
   `127.0.0.1`, no `localhost`.
4. Los datos de este diseño no se suben a git por mí: tú haces el commit/push.

## Riesgos conocidos

- El nombre exacto del tipo "Scopus Author ID" en la API de ORCID no se ha probado
  contra la API real; si no lo detecta, se imprime el JSON crudo y se ajusta.
- La prueba completa depende de tus credenciales sandbox en `config.ini`.
