# TIFF Spot White

Cross-platform desktop app for adding a Photoshop/RIP-style spot channel named
`white` to a single TIFF image. The generated spot mask is exact: pixels where
CMYK is `0,0,0,0` and alpha is greater than zero receive spot intensity equal to
alpha; all other pixels receive zero.

## Run

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m tiff_spot_white.gui
```

On Windows:

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
.\.venv\Scripts\python -m tiff_spot_white.gui
```

## Test

```bash
.venv/bin/python -m pytest
```

## Build Single-File Executables

macOS builds must be created on macOS, and Windows builds must be created on
Windows. The build scripts install PyInstaller into the active Python
environment, build the one-file executable, then run a bundled smoke test.

macOS:

```bash
scripts/build_macos.sh
```

Windows:

```powershell
.\scripts\build_windows.ps1
```

Outputs:

```text
dist/Tiff Spot White
dist/Tiff Spot White.exe
```

The executable also supports:

```bash
"dist/Tiff Spot White" --version
"dist/Tiff Spot White" --self-test
```

## Notes

The writer stores the spot mask as an additional TIFF channel and adds TIFF ink
tags plus Photoshop Image Resource metadata for alpha/spot channel names,
display info, alpha identifiers, and alternate spot colors. Programmatic
validation checks that this metadata exists, but Photoshop/RIP interpretation
still depends on the consuming software.
