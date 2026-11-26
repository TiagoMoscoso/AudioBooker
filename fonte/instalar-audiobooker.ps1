#requires -Version 5.1
<#
Instala (ou conserta) o ambiente do Audiobooker neste computador. Pode rodar de novo quando quiser (idempotente).
Requisito: o programa uv (winget install astral-sh.uv). Ele baixa o Python 3.11 sozinho.
O ambiente Python e os modelos ficam em %LOCALAPPDATA%\AUDIOBOOKER (ou na pasta da variavel AUDIOBOOKER_LOCAL).
  -Simular   so mostra o que faria
  -SemChatterbox   nao instala o Chatterbox (motor padrao: clonagem, emocao, maior qualidade)
  -ComKokoro       tambem instala o Kokoro (leve e rapido, ~350 MB; vozes prontas en/pt-BR, pronuncia por IPA)
  -ComPiper        tambem instala o Piper (vozes externas pequenas, CPU)
  Motores de terceiros: ver motores_extras_exemplo\ (copiar para %LOCALAPPDATA%\AUDIOBOOKER\motores_extras).
#>
param([switch]$Simular, [switch]$SemChatterbox, [switch]$ComKokoro, [switch]$ComPiper)

# O uv escreve progresso em stderr: no PowerShell 5.1 isso viraria erro com 'Stop'. Os erros reais vem do codigo de saida.
$ErrorActionPreference = 'Continue'
$Fonte = $PSScriptRoot
$Local = if ($env:AUDIOBOOKER_LOCAL) { $env:AUDIOBOOKER_LOCAL } else { Join-Path $env:LOCALAPPDATA 'AUDIOBOOKER' }
$Venv  = Join-Path $Local 'venv'
$Py    = Join-Path $Venv 'Scripts\python.exe'

function Etapa($t) { Write-Host "== $t" }
function Ok($t)    { Write-Host "   ok  $t" -ForegroundColor Green }
function Aviso($t) { Write-Host "   !   $t" -ForegroundColor Yellow }
function Erro($t)  { Write-Host "   x   $t" -ForegroundColor Red }
function Info($t)  { Write-Host "       $t" }

function Rodar([string]$desc, [scriptblock]$bloco) {
    if ($Simular) { Info "(simulado) $desc"; return }
    Info $desc
    & $bloco
    if ($LASTEXITCODE -ne 0) { throw "Falhou: $desc" }
}

try {
    Etapa 'Audiobooker: preparar o computador'
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Erro 'O programa uv nao foi encontrado. Instale com:  winget install astral-sh.uv'
        exit 1
    }
    New-Item -ItemType Directory -Force $Local | Out-Null

    $nvidia = $false
    try { $nvidia = [bool](Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match 'NVIDIA' }) } catch {}
    Info ("Placa NVIDIA: " + $(if ($nvidia) { 'sim (Chatterbox usara CUDA)' } else { 'nao (Chatterbox roda na CPU; Kokoro tenta DirectML e cai para CPU)' }))

    Etapa 'Ambiente Python 3.11'
    if (-not (Test-Path $Py)) { Rodar 'criando o ambiente' { uv venv --python 3.11 $Venv } } else { Ok 'ambiente ja existe' }

    Etapa 'Pacotes'
    Rodar 'pacotes principais' { uv pip install --python $Py -r (Join-Path $Fonte 'requisitos.txt') }
    if (-not $SemChatterbox) {
        if ($nvidia) {
            Rodar 'PyTorch com CUDA' { uv pip install --python $Py 'torch==2.6.0' 'torchaudio==2.6.0' --index-url https://download.pytorch.org/whl/cu124 }
        }
        # o Chatterbox exige numpy 1.x (o kokoro-onnx declara numpy 2, mas funciona com 1.26: testado)
        Rodar 'Chatterbox (clonagem de voz)' { uv pip install --python $Py chatterbox-tts 'setuptools<81' 'numpy<2' }
    }
    $env:PYTHONPATH = $Fonte
    if ($ComKokoro -or $ComPiper) {
        Etapa 'Motores opcionais (Kokoro / Piper)'
        Rodar 'pacotes' { uv pip install --python $Py -r (Join-Path $Fonte 'requisitos-opcionais.txt') }
        # esses pacotes puxam o onnxruntime comum, que esconde as placas de video: deixa so UMA variante
        #   NVIDIA -> onnxruntime-gpu (CUDA 12; as DLLs do CUDA/cuDNN vem do PyTorch cu124 instalado acima)
        #   AMD/Intel -> onnxruntime-directml (o Kokoro testa e cai para CPU se a placa nao aguentar)
        #   (1.22.0 e a ultima versao feita para CUDA 12; as seguintes exigem CUDA 13 e o PyTorch cu124 so traz CUDA 12)
        $variante = if ($nvidia -and -not $SemChatterbox) { 'onnxruntime-gpu==1.22.0' } else { 'onnxruntime-directml' }
        Rodar "onnxruntime ($variante)" {
            uv pip uninstall --python $Py onnxruntime onnxruntime-directml onnxruntime-gpu 2>$null
            uv pip install --python $Py $variante
        }
        if ($ComKokoro) { Rodar 'baixando o Kokoro (so na primeira vez)' { & $Py -m audiobooker baixar kokoro } }
    }
    # O modelo do Chatterbox (~3 GB) baixa sozinho na primeira geracao, ou em Configuracoes > Baixar.

    Etapa 'Teste'
    if (-not $Simular) { & $Py -m audiobooker dispositivos }
    Ok 'pronto: abra o Audiobooker com fonte\abrir-audiobooker.ps1'
} catch {
    Erro $_.Exception.Message
    exit 1
}
