#!/usr/bin/env bash
# Installs a Linux launcher entry (icon + menu/taskbar shortcut) for an
# already-built dist/Audiobooker (per §2 "ícone do launcher Linux").
#
# PyInstaller has no equivalent of Windows' .exe icon embedding on Linux —
# the launcher icon comes exclusively from a .desktop file's Icon= key, so
# this step is required (not optional) to get an icon in menus/taskbars/docks.
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"

EXE="$PROJECT_ROOT/dist/Audiobooker/Audiobooker"
if [ ! -x "$EXE" ]; then
    echo "Erro: $EXE não encontrado. Rode scripts/build_linux.sh primeiro." >&2
    exit 1
fi

LOGO_SRC="$PROJECT_ROOT/logo.png"
if [ ! -f "$LOGO_SRC" ]; then
    echo "Erro: logo.png não encontrado na raiz do projeto." >&2
    exit 1
fi

ICON_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$ICON_DIR" "$APPS_DIR"

cp "$LOGO_SRC" "$ICON_DIR/audiobooker.png"

sed \
    -e "s|__EXEC_PATH__|$EXE|" \
    -e "s|__ICON_PATH__|audiobooker|" \
    "$PROJECT_ROOT/scripts/audiobooker.desktop.in" > "$APPS_DIR/audiobooker.desktop"
chmod +x "$APPS_DIR/audiobooker.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

echo "Launcher instalado: $APPS_DIR/audiobooker.desktop"
echo "Ícone instalado: $ICON_DIR/audiobooker.png"
echo "Pode ser necessário reiniciar o menu de aplicativos/painel para o ícone aparecer."
