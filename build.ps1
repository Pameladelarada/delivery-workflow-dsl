$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (!(Test-Path "bin")) {
    New-Item -ItemType Directory -Path "bin" | Out-Null
}

$source = "compiler\main.cpp"
$output = "bin\delivery_compiler.exe"

if (!(Test-Path $source)) {
    Write-Host "No se encontro $source."
    Write-Host "Ejecuta este script desde la carpeta raiz del proyecto."
    exit 1
}

$gpp = Get-Command g++ -ErrorAction SilentlyContinue
$clang = Get-Command clang++ -ErrorAction SilentlyContinue
$cl = Get-Command cl -ErrorAction SilentlyContinue

try {
    if ($gpp) {
        Write-Host "Usando compilador: $($gpp.Source)"
        & $gpp.Source -std=c++17 -O2 -Wall -Wextra $source -o $output
    } elseif ($clang) {
        Write-Host "Usando compilador: $($clang.Source)"
        & $clang.Source -std=c++17 -O2 -Wall -Wextra $source -o $output
    } elseif ($cl) {
        Write-Host "Usando compilador: $($cl.Source)"
        & $cl.Source /EHsc /std:c++17 /Fe:$output $source
    } else {
        Write-Host "No se encontro un compilador C++."
        Write-Host "Instala MinGW-w64, LLVM/Clang o Visual Studio Build Tools."
        Write-Host "Opcion recomendada en Windows: instalar MinGW-w64 y agregar su carpeta bin al PATH."
        Write-Host "Luego cierra y vuelve a abrir PowerShell, y ejecuta: .\build.ps1"
        exit 1
    }
} catch {
    Write-Host "Fallo la compilacion."
    Write-Host $_.Exception.Message
    exit 1
}

Write-Host "Compilador generado en $output"
