#!/usr/bin/env bash
# Sets up the Audiobooker development environment on Linux (§3).
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3.11}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Erro: $PYTHON_BIN não encontrado. Instale Python 3.11 e tente novamente." >&2
    exit 1
fi

if [ ! -d .venv ]; then
    echo "Criando ambiente virtual (.venv) com $PYTHON_BIN..."
    "$PYTHON_BIN" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "Atualizando pip..."
pip install --upgrade pip wheel setuptools -q

echo "Instalando dependências do projeto..."
pip install -e .

echo ""
echo "Ambiente pronto. Para executar:"
echo "  source .venv/bin/activate"
echo "  python src/main.py"
