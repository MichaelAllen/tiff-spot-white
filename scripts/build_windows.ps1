$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$env:PYINSTALLER_CONFIG_DIR = Join-Path $Root "build\pyinstaller-cache"

$Python = "python"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $Python = $VenvPython
}

& $Python -m pip install --upgrade pip setuptools wheel
& $Python -m pip install --no-build-isolation -e ".[build]"
& $Python -m PyInstaller --clean --noconfirm packaging\pyinstaller\tiff_spot_white.spec
$Executable = Join-Path $Root "dist\Tiff Spot White.exe"
& $Executable --self-test

Write-Host "Built: $Executable"
