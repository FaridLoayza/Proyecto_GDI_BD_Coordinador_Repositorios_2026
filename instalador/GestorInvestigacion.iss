; Instalador de Windows del Sistema Gestor de Investigación (Inno Setup 6).
; Lo compila el workflow .github/workflows/release-windows.yml:
;   iscc /DVersion=1.5.2 /DOrigen=<carpeta con los archivos> instalador\GestorInvestigacion.iss
;
; Instala por usuario (sin permisos de administrador) en
; %LOCALAPPDATA%\Programs\GestorInvestigacion, así config.ini queda en el
; perfil del usuario. Solo la instalación de WSL2/Docker Desktop pide
; permisos de administrador (lo hace preparar.ps1).

#ifndef Version
  #define Version "0.0.0"
#endif
#ifndef Origen
  #define Origen "..\dist-instalador"
#endif

[Setup]
AppId={{6F3A2C8E-9B41-4C7A-8E2D-5A1B7C9D0E31}
AppName=Sistema Gestor de Investigación
AppVersion={#Version}
AppPublisher=Grupo 01 - GDI
DefaultDirName={localappdata}\Programs\GestorInvestigacion
DefaultGroupName=Sistema Gestor de Investigación
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=GestorInvestigacion-Setup-v{#Version}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=Sistema Gestor de Investigación {#Version}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Messages]
spanish.WelcomeLabel2=Se instalará el Sistema Gestor de Investigación {#Version}.%n%nEl instalador usa Docker Desktop para la base de datos PostgreSQL. Si no está instalado, se descargará e instalará (requiere permisos de administrador, conexión a Internet y, normalmente, reiniciar el equipo).

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "{#Origen}\GestorInvestigacion.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Origen}\config.ini.example"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Origen}\docker-compose.yml"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Origen}\preparar.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Origen}\LEEME.txt"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "{#Origen}\CREDENCIALES_PRUEBA.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Origen}\reporte_counter5_PR_2026_ejemplo.json"; DestDir: "{app}\ejemplos"; Flags: ignoreversion

[Icons]
Name: "{group}\Sistema Gestor de Investigación"; Filename: "{app}\GestorInvestigacion.exe"; WorkingDir: "{app}"
Name: "{group}\Preparar Sistema Gestor de Investigación (Docker y base de datos)"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\preparar.ps1"" -Carpeta ""{app}"""; WorkingDir: "{app}"
Name: "{group}\Desinstalar Sistema Gestor de Investigación"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Sistema Gestor de Investigación"; Filename: "{app}\GestorInvestigacion.exe"; WorkingDir: "{app}"; Tasks: escritorio

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\preparar.ps1"" -Carpeta ""{app}"""; WorkingDir: "{app}"; StatusMsg: "Preparando Docker y la base de datos (puede tardar varios minutos)..."; Flags: waituntilterminated
Filename: "{app}\GestorInvestigacion.exe"; Description: "Abrir el Sistema Gestor de Investigación"; WorkingDir: "{app}"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; Los datos de la base quedan en el volumen de Docker "gestor-investigacion_datos_postgres"
; y no se borran al desinstalar. config.ini y .env se conservan para una reinstalación.
Type: files; Name: "{app}\*.log"
