$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

python -m pip install -e ".[build]"
python -m PyInstaller --clean --noconfirm packaging\pyinstaller\tiff_spot_white.spec
& (Join-Path $Root "dist\Tiff Spot White.exe") --self-test

Write-Host "Built: $(Join-Path $Root 'dist\Tiff Spot White.exe')"
