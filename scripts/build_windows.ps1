# Builds the Audiobooker Windows executable (§45).
#
# Uses --onedir, not --onefile: PyTorch + CUDA + PySide6/Qt + Chatterbox
# pull in a large, native-extension-heavy dependency tree. --onefile's
# self-extracting temp-directory model is fragile at this size (slow first
# launch, CUDA/Qt plugin discovery issues when run from a temp extract
# path), so we keep the app as a directory of files
# (dist\Audiobooker\Audiobooker.exe), consistent with the spec's explicit
# "if onedir is more stable, use it".
$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "Verificando ambiente..."
if (-not (Test-Path ".venv")) {
    Write-Error ".venv não encontrado. Rode scripts\setup_windows.ps1 primeiro."
    exit 1
}
& ".venv\Scripts\Activate.ps1"

python -c "import PySide6, chatterbox, torch" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Dependências ausentes. Rode scripts\setup_windows.ps1."
    exit 1
}

pip install -q pyinstaller pillow

Write-Host "Preparando recursos..."
$LogoSrc = "logo.png"
if (-not (Test-Path $LogoSrc)) {
    $LogoSrc = "src\presentation\resources\logo.png"
}
$IcoPath = "build_resources\audiobooker.ico"
New-Item -ItemType Directory -Force -Path "build_resources" | Out-Null

Write-Host "Convertendo logo.png -> audiobooker.ico..."
python -c @"
from PIL import Image
img = Image.open(r'$LogoSrc').convert('RGBA')
sizes = [(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]
img.save(r'$IcoPath', format='ICO', sizes=sizes)
print('icon written to', r'$IcoPath')
"@

Write-Host "Limpando builds anteriores..."
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist

# transformers and diffusers (both pulled in by chatterbox-tts) probe
# importlib.metadata.version(...) for several of their own dependencies at
# import time (see transformers/dependency_versions_check.py and
# diffusers/dependency_versions_check.py) and raise if that package's
# .dist-info metadata isn't present, even if the package itself imports
# fine. --collect-all bundles code/data/binaries but NOT metadata; that
# needs the separate --copy-metadata flag. Confirmed by hitting this for
# real on Linux: a build without these flags failed at startup with
# "No package metadata was found for ... 'requests' distribution ...",
# raised by diffusers checking for requests/filelock/numpy.
# accelerate is deliberately excluded: it isn't an installed dependency,
# and transformers' own check skips it when absent — passing it here for an
# uninstalled package makes PyInstaller fail the build outright.
$MetadataPackages = @(
    "chatterbox-tts", "transformers", "diffusers", "torch", "torchaudio",
    "tqdm", "regex", "packaging", "filelock", "numpy", "tokenizers", "huggingface-hub",
    "safetensors", "pyyaml", "requests", "resemble-perth", "conformer",
    "librosa", "s3tokenizer", "omegaconf", "pyloudnorm"
)
$CopyMetadataArgs = $MetadataPackages | ForEach-Object { "--copy-metadata", $_ }

Write-Host "Executando PyInstaller..."
pyinstaller `
    --name Audiobooker `
    --onedir `
    --windowed `
    --icon "$IcoPath" `
    --add-data "$LogoSrc;presentation/resources" `
    --paths src `
    --collect-all chatterbox `
    --collect-all perth `
    --collect-all torch `
    --collect-all transformers `
    @CopyMetadataArgs `
    src/main.py

if (Test-Path "dist\Audiobooker\Audiobooker.exe") {
    Write-Host ""
    Write-Host "Build concluído: dist\Audiobooker\Audiobooker.exe"
} else {
    Write-Error "Artefato esperado não encontrado em dist\Audiobooker\Audiobooker.exe"
    exit 1
}
