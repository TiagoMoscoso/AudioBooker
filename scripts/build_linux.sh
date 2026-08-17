#!/usr/bin/env bash
# Builds the Audiobooker Linux executable (§45).
#
# Uses --onedir, not --onefile: PyTorch + CUDA + PySide6/Qt + Chatterbox
# pull in a large, native-extension-heavy dependency tree (CUDA .so files,
# Qt plugins, model-loading shared libraries). --onefile's self-extracting
# temp-directory model is fragile with graphs this size (slow first launch,
# and some CUDA/Qt plugin discovery breaks when running from a temp extract
# path) and is not the more stable choice here, so we keep the app as a
# directory of files (dist/Audiobooker/Audiobooker), consistent with the
# spec's explicit "if onedir is more stable, use it".
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
    echo "Erro: .venv não encontrado. Rode scripts/setup_linux.sh primeiro." >&2
    exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "Verificando ambiente..."
python -c "import PySide6, chatterbox, torch" || {
    echo "Erro: dependências ausentes. Rode scripts/setup_linux.sh." >&2
    exit 1
}

pip install -q pyinstaller

echo "Limpando builds anteriores..."
rm -rf build dist

LOGO_SRC="logo.png"
if [ ! -f "$LOGO_SRC" ]; then
    LOGO_SRC="src/presentation/resources/logo.png"
fi

# transformers and diffusers (both pulled in by chatterbox-tts) probe
# `importlib.metadata.version(...)` for several of their own dependencies at
# import time (see transformers/dependency_versions_check.py and
# diffusers/dependency_versions_check.py) and raise if the package's
# .dist-info metadata isn't present — even if the package itself imports
# fine. `--collect-all` bundles code/data/binaries but NOT metadata; that
# needs the separate `--copy-metadata` flag. Confirmed by hitting this for
# real: a build without these flags failed at startup with
# "No package metadata was found for ... 'requests' distribution ...",
# raised by diffusers checking for requests/filelock/numpy.
# accelerate is deliberately NOT in this list: it isn't an installed
# dependency here, and transformers' own check skips it when absent
# (`is_accelerate_available()` guard) — passing it to --copy-metadata for a
# package that isn't installed makes PyInstaller fail the build outright.
METADATA_PACKAGES=(
    chatterbox-tts transformers diffusers torch torchaudio
    tqdm regex packaging filelock numpy tokenizers huggingface-hub
    safetensors pyyaml requests resemble-perth conformer
    librosa s3tokenizer omegaconf pyloudnorm
)
COPY_METADATA_ARGS=()
for pkg in "${METADATA_PACKAGES[@]}"; do
    COPY_METADATA_ARGS+=(--copy-metadata "$pkg")
done

echo "Executando PyInstaller..."
pyinstaller \
    --name Audiobooker \
    --onedir \
    --windowed \
    --add-data "${LOGO_SRC}:presentation/resources" \
    --paths src \
    --collect-all chatterbox \
    --collect-all perth \
    --collect-all torch \
    --collect-all transformers \
    "${COPY_METADATA_ARGS[@]}" \
    src/main.py

echo ""
if [ -f "dist/Audiobooker/Audiobooker" ]; then
    echo "Build concluído: dist/Audiobooker/Audiobooker"
else
    echo "Aviso: artefato esperado não encontrado em dist/Audiobooker/Audiobooker" >&2
    exit 1
fi

echo "Instalando ícone/launcher Linux..."
scripts/install_linux.sh
