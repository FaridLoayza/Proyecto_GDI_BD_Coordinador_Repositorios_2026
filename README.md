# Gestor de Investigación - Aplicativo (Grupo 01)

Aplicativo web para registrar y revisar postulaciones de investigadores, gestionar
solicitudes de patentes e importar publicaciones de investigación. Utiliza PostgreSQL
16; el backend está desarrollado en Python con FastAPI y consultas SQL mediante
`psycopg2`, sin ORM.

## Funcionalidades

- Registro de investigadores y revisión de postulaciones por coordinación.
- Registro y seguimiento de solicitudes de patentes.
- Importación de publicaciones desde CSV de Pure y revisión de registros pendientes.
- **Histórico (seguimiento del uso de repositorios):** resumen del repositorio
  (publicaciones por año, tipo, escuela y ODS), catálogo de publicaciones, **uso de
  las suscripciones de biblioteca** (ScienceDirect, Scopus, ClinicalKey, Engineering
  Village…) por plataforma y mes, con gráfico y exportación CSV, e importación de
  reportes **COUNTER 5** (JSON o CSV). Los datos de uso son agregados: no hay datos
  por estudiante. Ejemplo para importar:
  `backend/database/ejemplos/reporte_counter5_PR_2026_ejemplo.json`.
- Descarga automática del uso por **SUSHI** (Elsevier) preparada y apagada: se activa
  con la sección `[sushi]` de `config.ini` cuando la biblioteca entregue sus
  credenciales COUNTER.
- Directorio de investigadores y reportes del repositorio.
- 15 reportes (consultas) implementados como procedimientos almacenados
  `sp_reporte_01` ... `sp_reporte_15`; 8 de ellos usan JOIN.
- Borrado lógico de investigadores, patentes y publicaciones: "dar de baja" y
  "reactivar" mediante `sp_eliminar_*` y `sp_reactivar_*` (los registros no se borran).
- Panel de administrador con CRUD sobre todas las tablas mediante los procedimientos
  `sp_admin_insertar`, `sp_admin_actualizar` y `sp_admin_eliminar`.
- Ejecutable de Windows `GestorInvestigacion.exe` (sección *Ejecutable de Windows*).

Las cuentas de prueba están en [CREDENCIALES_PRUEBA.md](CREDENCIALES_PRUEBA.md).

## Estructura

```text
gestor-investigacion/
  backend/
    api/                         API web
    config.ini.example           Plantilla de conexión a PostgreSQL
    requirements.txt             Dependencias de Python
    database/
      base_datos_repositorio.sql Script completo: tablas, procedimientos, triggers y datos de prueba
      instalar_bd.py             Instalador del esquema
      crear_admin.py             Crea la cuenta de administrador del portal
    lanzador_windows.py          Punto de entrada de GestorInvestigacion.exe
    pruebas/                      Pruebas del backend y la base de datos
    src/db/conexion.py            Conexión y consultas PostgreSQL
  frontend/
    portal/                       Aplicación web en React y Vite
  empaquetado/                    Archivos que acompañan al .exe en el release
  .github/workflows/              Generación automática del release para Windows
```

## Puesta en marcha

Los comandos de Python y npm funcionan tanto en **CMD** como en **PowerShell**.
Cuando cambia el directorio, se incluyen los comandos específicos de cada terminal.

1. Instalar Python 3.10 o superior, Node.js con npm y PostgreSQL 16.
2. Desde la raíz del proyecto, instalar las dependencias del backend:

   ```cmd
   python -m pip install -r backend\requirements.txt
   ```

3. Si aún no existe `backend\config.ini`, copia `backend\config.ini.example` usando
   el comando correspondiente y configura la conexión a PostgreSQL
   (`dbname = bd_coordinador_repositorios`):

   CMD:

   ```cmd
   copy backend\config.ini.example backend\config.ini
   ```

   PowerShell:

   ```powershell
   Copy-Item backend\config.ini.example backend\config.ini
   ```

   La contraseña también puede proporcionarse con la variable de entorno `UCSM_DB_PASSWORD`.
   Para el inicio de sesión con ORCID, completar también la sección `[orcid]`
   (`client_id`, `client_secret`, `environment`, `redirect_uri`, `frontend_origin`)
   con los datos de la app registrada en `sandbox.orcid.org`. El `redirect_uri` debe
   ser idéntico al registrado (`http://127.0.0.1:8000/api/auth/orcid/callback`) y el
   navegador debe abrirse siempre en `127.0.0.1`, no en `localhost`, para que la
   sesión no se pierda al volver de ORCID.
4. Solo para una instalación nueva, instala el esquema en una base vacía. El instalador
   crea `bd_coordinador_repositorios` si no existe y se niega a modificar una base que
   ya contiene tablas:

   ```cmd
   python backend\database\instalar_bd.py
   ```

5. Iniciar la API en modo desarrollo desde la raíz del proyecto:

   ```cmd
   python -m uvicorn backend.api.app:app --reload
   ```

6. En otra terminal, iniciar el frontend:

   CMD:

   ```cmd
   cd /d frontend\portal
   npm ci
   npm run dev
   ```

   PowerShell:

   ```powershell
   Set-Location frontend\portal
   npm ci
   npm run dev
   ```

   Abrir `http://127.0.0.1:5173`. El frontend se comunica con el backend en
   `http://127.0.0.1:8000`.

Para usar la interfaz compilada servida por FastAPI, compílala desde la raíz del proyecto.
En CMD:

```cmd
cd /d frontend\portal
npm ci
npm run build
cd /d ..\..
```

En PowerShell:

```powershell
Set-Location frontend\portal
npm ci
npm run build
Set-Location ..\..
```

Luego inicia el backend desde la raíz (el comando es igual en CMD y PowerShell):

```cmd
python -m backend.api
```

Luego abre `http://127.0.0.1:8000`. En este modo solo se inicia el backend Python,
porque FastAPI sirve los archivos compilados del frontend.

## Cuentas de administrador

Hay dos cuentas de administrador, independientes del flujo investigador/coordinador:

- **Panel admin del portal** (`/login/admin` → `/admin`): consulta, crea, edita y
  elimina registros de cualquier tabla. Las restricciones, claves foráneas y
  triggers de la base se siguen aplicando. Para crear o cambiar la cuenta:

  ```cmd
  python backend\database\crear_admin.py
  ```

  Con el ejecutable de Windows: `GestorInvestigacion.exe --crear-admin`.

- Opcionalmente, la sección `[postgresql_admin]` de `config.ini` hace que el panel
  admin se conecte a la base con ese rol.

## Ejecutable de Windows

Cada tag `vX.Y.Z` publica en *Releases* un `.zip` con la carpeta EJECUTABLE:
`GestorInvestigacion.exe`, `Gestor de Investigación.cmd` (archivo de inicio que funciona desde cualquier
ruta), `Gestor de Investigación.url` (acceso directo a `http://127.0.0.1:8000`), `config.ini.example`,
`LEEME.txt`, `CREDENCIALES_PRUEBA.txt` y el SQL de instalación. Solo requiere PostgreSQL 16:

```cmd
GestorInvestigacion.exe --instalar-bd
```

crea la base con el esquema y los datos de prueba, y `GestorInvestigacion.exe --crear-admin`
crea una cuenta de administrador.

## Pruebas

Para comprobar la conexión a PostgreSQL:

```cmd
python backend\pruebas\prueba_conexion.py
```

Las pruebas del portal y del instalador pueden ejecutarse así:

```cmd
python -m unittest backend.pruebas.prueba_portal_web
python -m unittest backend.pruebas.prueba_uso_suscripciones
python backend\pruebas\prueba_instalador_bd.py
```

Las pruebas de CRUD, triggers y reportes requieren que la conexión a PostgreSQL esté
configurada en `backend/config.ini`.
