#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PYINSTALLER_CONFIG_DIR="$ROOT/build/pyinstaller-cache"

PYTHON="${PYTHON:-python3}"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

"$PYTHON" -m pip install --no-build-isolation -e ".[build]"
"$PYTHON" -m PyInstaller --clean --noconfirm packaging/pyinstaller/tiff_spot_white.spec
"$ROOT/dist/Tiff Spot White" --self-test

echo "Built: $ROOT/dist/Tiff Spot White"
echo "Built app bundle: $ROOT/dist/Tiff Spot White.app"
