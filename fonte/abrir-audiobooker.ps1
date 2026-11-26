#requires -Version 5.1
<# Abre o Audiobooker. Se o ambiente ainda nao existe, instala antes.
   -Console   abre com janela de console para ver mensagens de erro #>
param([switch]$Console)

$Fonte = $PSScriptRoot
$Local = if ($env:AUDIOBOOKER_LOCAL) { $env:AUDIOBOOKER_LOCAL } else { Join-Path $env:LOCALAPPDATA 'AUDIOBOOKER' }
$Venv  = Join-Path $Local 'venv\Scripts'
$Exe   = Join-Path $Venv $(if ($Console) { 'python.exe' } else { 'pythonw.exe' })

if (-not (Test-Path $Exe)) {
    Write-Host '== Primeira vez neste PC: preparando o Audiobooker (alguns minutos)'
    & (Join-Path $Fonte 'instalar-audiobooker.ps1')
    if (-not (Test-Path $Exe)) { exit 1 }
}

New-Item -ItemType Directory -Force (Join-Path $Local 'logs') | Out-Null
$env:PYTHONPATH = $Fonte
$env:PYTHONUTF8 = '1'
Start-Process -FilePath $Exe -ArgumentList '-m', 'audiobooker.interface.app' -WorkingDirectory $Fonte `
    -WindowStyle Normal
