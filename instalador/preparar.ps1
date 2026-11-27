<#
  Preparación del Sistema Gestor de Investigación (la ejecuta el instalador).

  1. Comprueba WSL2 y Docker Desktop. Si faltan, los instala (pide permisos de
     administrador) y, si Windows lo necesita, pide reiniciar. Tras el reinicio
     este script continúa solo (RunOnce).
  2. Inicia Docker Desktop y espera a que responda.
  3. La primera vez: genera una contraseña aleatoria para PostgreSQL y una clave
     de sesión, y escribe .env y config.ini (solo accesibles para este usuario).
  4. Levanta el contenedor PostgreSQL 16 (docker-compose.yml).
  5. Si la base no existe, la instala con GestorInvestigacion.exe --instalar-bd.

  La contraseña aleatoria se cambia en el asistente de primer inicio del portal.
#>
param(
    [Parameter(Mandatory = $true)][string]$Carpeta
)

$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'Sistema Gestor de Investigación - Preparación'
Add-Type -AssemblyName System.Windows.Forms
Set-Location $Carpeta

$ScriptPropio = Join-Path $Carpeta 'preparar.ps1'
$Compose = Join-Path $Carpeta 'docker-compose.yml'
$EnvFile = Join-Path $Carpeta '.env'
$ConfigFile = Join-Path $Carpeta 'config.ini'
$Exe = Join-Path $Carpeta 'GestorInvestigacion.exe'
$DockerUrl = 'https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe'
$Titulo = 'Sistema Gestor de Investigación'

function Paso($texto) { Write-Host ''; Write-Host "==> $texto" -ForegroundColor Green }
function Aviso($texto, $icono = 'Information') {
    [System.Windows.Forms.MessageBox]::Show($texto, $Titulo, 'OK', $icono) | Out-Null
}

function Docker-Instalado { [bool](Get-Command docker -ErrorAction SilentlyContinue) -or (Test-Path "$env:ProgramFiles\Docker\Docker\resources\bin\docker.exe") }
function Docker-Responde {
    try { & docker info *> $null; return $LASTEXITCODE -eq 0 } catch { return $false }
}
function Wsl-Listo {
    try { & wsl.exe --status *> $null; return $LASTEXITCODE -eq 0 } catch { return $false }
}

function Pedir-Reinicio {
    # Continúa automáticamente la próxima vez que el usuario inicie sesión.
    $comando = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$ScriptPropio`" -Carpeta `"$Carpeta`""
    New-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce' `
        -Name 'GestorInvestigacionPreparacion' -Value $comando -PropertyType String -Force | Out-Null
    $respuesta = [System.Windows.Forms.MessageBox]::Show(
        "Se instalaron componentes de Windows necesarios para Docker (WSL2 / Docker Desktop).`n`n" +
        "Se necesita REINICIAR el equipo para poder usar el Sistema Gestor de Investigación.`n" +
        "Al volver a iniciar sesión, la preparación continuará sola.`n`n¿Reiniciar ahora?",
        $Titulo, 'YesNo', 'Warning')
    if ($respuesta -eq 'Yes') { Restart-Computer -Force }
    exit 0
}

function Clave-Aleatoria([int]$largo) {
    $caracteres = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'.ToCharArray()
    $bytes = New-Object byte[] $largo
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    -join ($bytes | ForEach-Object { $caracteres[$_ % $caracteres.Length] })
}

function Puerto-Libre {
    foreach ($p in 5433..5450) {
        $l = $null
        try { $l = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $p); $l.Start(); return $p }
        catch { } finally { if ($l) { $l.Stop() } }
    }
    throw 'No hay un puerto libre entre 5433 y 5450 para la base de datos.'
}

function Solo-Usuario($ruta) {
    & icacls.exe $ruta /inheritance:r /grant:r "$($env:USERNAME):(F)" *> $null
}

try {
    # 1. WSL2 y Docker Desktop ----------------------------------------------
    if (-not (Docker-Instalado)) {
        $reiniciar = $false
        if (-not (Wsl-Listo)) {
            Paso 'Instalando WSL2 (requisito de Docker). Acepte el permiso de administrador.'
            Start-Process wsl.exe -ArgumentList '--install', '--no-distribution' -Verb RunAs -Wait
            $reiniciar = $true
        }
        Paso 'Descargando Docker Desktop (unos 600 MB, puede tardar)...'
        $instaladorDocker = Join-Path $env:TEMP 'DockerDesktopInstaller.exe'
        Invoke-WebRequest -Uri $DockerUrl -OutFile $instaladorDocker -UseBasicParsing
        Paso 'Instalando Docker Desktop. Acepte el permiso de administrador.'
        $p = Start-Process $instaladorDocker -ArgumentList 'install', '--quiet', '--accept-license' -Verb RunAs -Wait -PassThru
        Remove-Item $instaladorDocker -ErrorAction SilentlyContinue
        if ($p.ExitCode -ne 0) { throw "El instalador de Docker Desktop terminó con código $($p.ExitCode)." }
        # Docker Desktop recién instalado necesita reiniciar (o volver a iniciar sesión).
        Pedir-Reinicio
    }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        $env:Path += ";$env:ProgramFiles\Docker\Docker\resources\bin"
    }

    # 2. Docker Desktop encendido ---------------------------------------------
    if (-not (Docker-Responde)) {
        Paso 'Iniciando Docker Desktop...'
        foreach ($ruta in "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe", "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe") {
            if (Test-Path $ruta) { Start-Process $ruta; break }
        }
        $limite = (Get-Date).AddMinutes(4)
        while (-not (Docker-Responde)) {
            if ((Get-Date) -gt $limite) {
                if (-not (Wsl-Listo)) { Pedir-Reinicio }
                throw 'Docker Desktop no respondió. Ábralo, acepte sus términos de uso y vuelva a ejecutar el acceso directo "Preparar Sistema Gestor de Investigación".'
            }
            Start-Sleep -Seconds 5
        }
    }

    # 3. Credenciales aleatorias (solo la primera vez) -------------------------
    if (-not (Test-Path $ConfigFile)) {
        Paso 'Generando credenciales aleatorias para la base de datos...'
        $clave = Clave-Aleatoria 24
        $secreto = Clave-Aleatoria 48
        $puerto = Puerto-Libre
        Set-Content -Path $EnvFile -Encoding ascii -Value @("POSTGRES_PASSWORD=$clave", "DB_PORT=$puerto")
        $plantilla = Get-Content (Join-Path $Carpeta 'config.ini.example') -Raw -Encoding UTF8
        $plantilla = $plantilla -replace '(?m)^port = .*$', "port = $puerto" `
                                -replace '(?m)^password = CAMBIAR_CLAVE\r?$', "password = $clave" `
                                -replace '(?m)^host = .*$', 'host = 127.0.0.1' `
                                -replace '(?m)^client_id = .*$', 'client_id =' `
                                -replace '(?m)^client_secret = .*$', 'client_secret ='
        $plantilla += "`n[portal]`nsession_secret = $secreto`nconfiguracion_inicial = pendiente`n" +
                      "`n[docker]`ncompose = $Compose`n"
        [System.IO.File]::WriteAllText($ConfigFile, $plantilla, (New-Object System.Text.UTF8Encoding($false)))
        Solo-Usuario $EnvFile
        Solo-Usuario $ConfigFile
    }

    # 4. Contenedor PostgreSQL ------------------------------------------------
    Paso 'Encendiendo PostgreSQL 16 en Docker (la primera vez descarga la imagen)...'
    & docker compose -f $Compose --env-file $EnvFile up -d
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo iniciar el contenedor de la base de datos.' }
    $limite = (Get-Date).AddMinutes(3)
    while ((& docker inspect -f '{{.State.Health.Status}}' gestor-investigacion-db) -ne 'healthy') {
        if ((Get-Date) -gt $limite) { throw 'La base de datos no terminó de iniciar.' }
        Start-Sleep -Seconds 3
    }

    # 5. Esquema y datos de prueba (solo si la base no existe) ------------------
    $existe = & docker exec gestor-investigacion-db psql -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'bd_coordinador_repositorios'"
    if ("$existe".Trim() -ne '1') {
        Paso 'Creando la base de datos con sus tablas y datos de prueba...'
        & $Exe --instalar-bd --sin-pausa
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar la base de datos.' }
    }

    Paso 'Preparación terminada.'
    Aviso "Todo está listo.`n`nAl abrir el Sistema Gestor de Investigación se mostrará la configuración inicial: cambiará la contraseña de la base de datos y podrá registrar sus credenciales de ORCID."
    exit 0
}
catch {
    Write-Host $_ -ForegroundColor Red
    Aviso "La preparación no pudo completarse:`n`n$($_.Exception.Message)`n`nPuede reintentarla con el acceso directo `"Preparar Sistema Gestor de Investigación`" del menú Inicio." 'Error'
    exit 1
}
