# Credenciales de prueba — Portal CRIS

Cuentas incluidas en los datos de prueba de `backend/database/base_datos_repositorio.sql`.
Son solo para evaluación y demostración: **cámbielas antes de usar el sistema con datos reales.**

| Perfil | Dónde ingresar | Correo | Contraseña | Estado en los datos de prueba |
|---|---|---|---|---|
| Coordinador de repositorios | `/login/coordinator` | `coord.demo@ucsm.edu.pe` | `CoordinadorDemo2026` | Activo |
| Investigador | `/login/investigator` | `investigador.aprobado@ucsm.edu.pe` | `Investigador2026` | Postulación aprobada (perfil y patentes) |
| Investigador | `/login/investigator` | `investigador.observado@ucsm.edu.pe` | `Investigador2026` | Postulación observada (puede corregir y reenviar) |
| Investigador | `/login/investigator` | `investigador.pendiente@ucsm.edu.pe` | `Investigador2026` | Postulación pendiente de revisión |
| Administrador | `/login/admin` | `admin@portalcris.pe` | `AdminDemo2026!` | Activo (panel de datos) |

Notas:

- Las contraseñas se guardan en la base solo como hash PBKDF2-SHA256.
- Para crear otra cuenta de administrador: `python backend/database/crear_admin.py`
  o `PortalCRIS.exe --crear-admin`.
- Rol de PostgreSQL `admin_cris` (CRUD sin DDL): no tiene contraseña por defecto; se crea con
  `backend/database/rol_admin_cris.sql` indicando la clave al ejecutarlo.
- El login con ORCID usa la cuenta personal del investigador en orcid.org (sandbox en pruebas).
