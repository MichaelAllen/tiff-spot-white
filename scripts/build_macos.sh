#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python -m pip install -e ".[build]"
python -m PyInstaller --clean --noconfirm packaging/pyinstaller/tiff_spot_white.spec
"$ROOT/dist/Tiff Spot White" --self-test

echo "Built: $ROOT/dist/Tiff Spot White"
