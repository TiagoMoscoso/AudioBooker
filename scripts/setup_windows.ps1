# Sets up the Audiobooker development environment on Windows (§3).
$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }

$versionOutput = & $PythonBin --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python não encontrado. Instale Python 3.11 e tente novamente."
    exit 1
}
Write-Host "Usando $versionOutput"

if (-not (Test-Path ".venv")) {
    Write-Host "Criando ambiente virtual (.venv)..."
    & $PythonBin -m venv .venv
}

& ".venv\Scripts\Activate.ps1"

Write-Host "Atualizando pip..."
pip install --upgrade pip wheel setuptools -q

Write-Host "Instalando dependências do projeto..."
pip install -e .

Write-Host ""
Write-Host "Ambiente pronto. Para executar:"
Write-Host "  .venv\Scripts\Activate.ps1"
Write-Host "  python src\main.py"
