@echo off
rem ==========================================================================
rem  Gestor de Investigación - archivo de inicio
rem  Inicia el sistema desde la carpeta donde esta este archivo (%~dp0), por lo
rem  que funciona aunque la carpeta se copie a otro equipo o a otra ruta.
rem ==========================================================================
cd /d "%~dp0"
if not exist "%~dp0config.ini" (
  echo No se encontro config.ini en esta carpeta.
  echo Copie config.ini.example como config.ini y complete los datos de PostgreSQL.
  echo Vea LEEME.txt para los pasos de instalacion.
  pause
  exit /b 1
)
start "Gestor de Investigación" "%~dp0GestorInvestigacion.exe"
