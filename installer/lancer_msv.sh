#!/usr/bin/env bash
# Lanceur de Montage Studio Video (version installée, macOS / Linux) : même logique que lancer_msv.bat.
set -euo pipefail
ICI="$(cd "$(dirname "$0")" && pwd)"
APP="$ICI/app"
UV="$ICI/uv"
if [ "$(uname)" = "Darwin" ]; then DATA="$HOME/Library/Application Support/MontageStudioVideo"
else DATA="${XDG_DATA_HOME:-$HOME/.local/share}/montage-studio-video"; fi
VENV="$DATA/venv"
export UV_CACHE_DIR="$DATA/uv-cache" UV_PYTHON_INSTALL_DIR="$DATA/python" UV_PYTHON_PREFERENCE=only-managed
export MSV_INSTALLED=1

if [ ! -x "$VENV/bin/python" ] || ! cmp -s "$APP/requirements.lock" "$VENV/requirements.lock"; then
  echo "Montage Studio Video : première configuration (une seule fois, 2 à 5 minutes)..."
  rm -rf "$VENV"
  "$UV" venv --python 3.12 "$VENV"
  "$UV" pip install --no-deps --python "$VENV/bin/python" -r "$APP/requirements.lock"
  cp "$APP/requirements.lock" "$VENV/requirements.lock"
fi
[ "${MSV_PREPARER_SEULEMENT:-0}" = "1" ] && exit 0
exec "$VENV/bin/python" "$APP/app.py" "$@"
