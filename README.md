# Repositorios UCSM - Aplicativo

Aplicativo web para registrar y revisar postulaciones de investigadores, gestionar
solicitudes de patentes e importar publicaciones de investigación. Utiliza PostgreSQL
16; el backend está desarrollado en Python con FastAPI y consultas SQL mediante
`psycopg2`, sin ORM.

## Funcionalidades

- Registro de investigadores y revisión de postulaciones por coordinación.
- Registro y seguimiento de solicitudes de patentes.
- Importación de publicaciones desde CSV de Pure y revisión de registros pendientes.
- Directorio de investigadores y reportes del repositorio.

## Estructura

```text
repositorios_ucsm/
  backend/
    api/                         API web
    config.ini.example           Plantilla de conexión a PostgreSQL
    requirements.txt             Dependencias de Python
    database/
      base_datos_repositorio.sql Esquema de la base de datos
      instalar_bd.py             Instalador del esquema
    pruebas/                      Pruebas del backend y la base de datos
    src/db/conexion.py            Conexión y consultas PostgreSQL
  frontend/
    portal/                       Aplicación web en React y Vite
```

## Puesta en marcha

1. Instalar Python 3.10 o superior, Node.js con npm y PostgreSQL 16.
2. Desde la raíz del proyecto, instalar las dependencias del backend:

   ```powershell
   python -m pip install -r backend/requirements.txt
   ```

3. Copiar `backend/config.ini.example` como `backend/config.ini` y configurar los datos
   de conexión a PostgreSQL (`dbname = bd_coordinador_repositorios`). La contraseña
   también puede proporcionarse con la variable de entorno `UCSM_DB_PASSWORD`.
4. Instalar el esquema en la base de datos. El instalador crea la base
   `bd_coordinador_repositorios` automáticamente si no existe:

   ```powershell
   python backend/database/instalar_bd.py
   ```

6. Iniciar FastAPI en modo desarrollo desde la raíz del proyecto:

   ```powershell
   fastapi dev backend/api/app.py
   ```

7. En otra terminal, iniciar el frontend:

   ```powershell
   Set-Location frontend\portal
   npm install
   npm run dev
   ```

   Abrir `http://127.0.0.1:5173`. El frontend se comunica con el backend en
   `http://127.0.0.1:8000`.

Para usar la interfaz compilada servida por FastAPI, compílala:

```powershell
Set-Location frontend\portal
npm run build
Set-Location ..\..
```

Luego inicia el backend desde la raíz:

```powershell
python -m backend.api
```

Luego abre `http://127.0.0.1:8000`. En este modo solo se inicia el backend Python,
porque FastAPI sirve los archivos compilados del frontend.

## Pruebas

Para comprobar la conexión a PostgreSQL:

```powershell
python backend/pruebas/prueba_conexion.py
```

Las pruebas del portal y del instalador pueden ejecutarse así:

```powershell
python -m unittest backend.pruebas.prueba_portal_web
python backend/pruebas/prueba_instalador_bd.py
```

Las pruebas de CRUD, triggers y reportes requieren que la conexión a PostgreSQL esté
configurada en `backend/config.ini`.
