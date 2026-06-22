$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$venvPython = ".\.venv\Scripts\python.exe"
$compiler = ".\bin\delivery_compiler.exe"
$url = "http://127.0.0.1:5000"

Write-Host "Proyecto: Trabajo final_compiladores"
Write-Host "Preparando entorno..."

if (!(Test-Path $venvPython)) {
    Write-Host "Creando entorno virtual .venv..."
    python -m venv .venv
}

Write-Host "Verificando Flask..."
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $venvPython -c "import flask" *> $null
$flaskInstalled = $LASTEXITCODE -eq 0
$ErrorActionPreference = $previousErrorActionPreference

if (!$flaskInstalled) {
    Write-Host "Instalando dependencias de requirements.txt..."
    & $venvPython -m pip install -r requirements.txt
}

if (!(Test-Path $compiler)) {
    Write-Host "Compilador C++ no encontrado. Ejecutando build.ps1..."
    powershell -ExecutionPolicy Bypass -File .\build.ps1
}

if (!(Test-Path $compiler)) {
    Write-Host "No se pudo generar $compiler."
    Write-Host "Revisa que tengas instalado un compilador C++ como MinGW-w64, LLVM/Clang o Visual Studio Build Tools."
    exit 1
}

Write-Host ""
Write-Host "Servidor listo. Abriendo navegador en $url"
Write-Host "Para detener el servidor, presiona CTRL + C en esta consola."
Start-Process $url
& $venvPython web\app.py
