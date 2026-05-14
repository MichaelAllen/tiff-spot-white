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

## Notes

The writer stores the spot mask as an additional TIFF channel and adds TIFF ink
tags plus Photoshop Image Resource metadata for alpha/spot channel names,
display info, alpha identifiers, and alternate spot colors. Programmatic
validation checks that this metadata exists, but Photoshop/RIP interpretation
still depends on the consuming software.
