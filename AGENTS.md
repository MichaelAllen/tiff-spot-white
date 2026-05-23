# Agent Handoff Notes

This repo is a small Python desktop application named **TIFF Spot White**. It adds a Photoshop/RIP-style spot channel named `white` to one input image and writes a new TIFF beside the input by default.

## What The App Does

- The core contract is in `src/tiff_spot_white/core.py`.
- The generated logical spot mask is exact: pixels where CMYK is `0,0,0,0` and alpha is greater than zero get spot intensity equal to alpha; all other pixels get zero.
- The logical mask uses `255` as full white-ink coverage, but Photoshop TIFF spot channels are stored with inverse polarity: stored `0` means full spot ink and stored `255` means no spot ink.
- Output path defaults to `<input_stem>_spotwhite.tiff`.
- Only the first page of a multi-page image is processed, with a warning.
- True CMYK TIFF inputs are read through `tifffile` so CMYK values, alpha, selected metadata, and existing extra channels can be preserved.
- Non-CMYK or fallback inputs are read through Pillow, converted to CMYK, and produce warnings because original color values cannot be preserved exactly.
- If there is no alpha channel, full opacity alpha is synthesized and a warning is emitted.

## Important Files

- `src/tiff_spot_white/core.py`: image loading, mask generation, TIFF writing, validation, and existing `white` channel handling.
- `src/tiff_spot_white/photoshop_resources.py`: minimal Photoshop Image Resource Block packing/parsing for alpha and spot channel metadata in TIFF tag `34377`.
- `src/tiff_spot_white/gui.py`: PySide6 GUI with drag/drop, preview, spot overlay preview, overwrite prompts, existing-spot prompts, and background conversion thread.
- `src/tiff_spot_white/__main__.py`: executable entrypoint, `--version`, and bundled `--self-test`.
- `tests/test_core.py`: core conversion and metadata tests, including real fixture checks when `tests/images/*` fixtures exist.
- `tests/test_gui.py`: lightweight GUI helper tests.
- `packaging/pyinstaller/tiff_spot_white.spec`: PyInstaller config for macOS app bundle and Windows exe.
- `scripts/build_macos.sh` and `scripts/build_windows.ps1`: platform build scripts that install build deps, run PyInstaller, then run the bundled self-test.
- `.github/workflows/build-and-test.yml`: CI matrix for macOS and Windows, running tests and platform builds without uploading artifacts.
- `.github/workflows/create-release.yml`: release workflow that builds both platforms, packages release assets, and creates a GitHub Release.

## GitHub And CI

- Remote repo: `git@github.com:Vulpine-Solutions/tiff-spot-white.git`
- GitHub URL: `https://github.com/Vulpine-Solutions/tiff-spot-white`
- Default branch is `main`.
- The CI workflow is `Build and test`.
- The release workflow is `Create release`.
- Pushes and pull requests run tests plus macOS/Windows builds, but do not upload executable artifacts.
- Releases are created by pushing a `v*` tag or running the release workflow manually with a tag name.
- Release assets are `tiff-spot-white-macos.zip` for the zipped `.app` bundle and `tiff-spot-white-windows.exe` for Windows.

## Conversion Details To Preserve

- `generate_spot_mask(cmyk, alpha)` should stay strict about input shapes and exact-white detection.
- `encode_photoshop_spot_channel()` and `decode_photoshop_spot_channel()` are intentionally inverse polarity helpers. Do not remove this inversion unless the Photoshop/RIP contract changes.
- `convert_image()` supports `existing_spot_action` values:
  - `cancel`: raise if an existing channel named `white` is present.
  - `alternate`: add the new channel as `white 2`.
  - `overwrite`: remove an existing non-alpha `white` channel and replace it.
- The first extra channel after CMYK is treated as preserved alpha for CMYK TIFFs. Existing extra channels after that are preserved before appending the new spot channel.
- Photoshop metadata resources are intentionally limited to the resources needed to name and identify alpha/spot channels:
  - `1006` alpha names
  - `1045` Unicode alpha names
  - `1053` alpha identifiers
  - `1067` alternate spot colors
  - `1077` display info float
- TIFF ink tags are written alongside Photoshop resources:
  - `332` InkSet
  - `333` InkNames
  - `334` NumberOfInks
  - `34377` Photoshop ImageResources
- Output TIFFs are written uncompressed with contiguous planar configuration and `photometric="separated"`.

## GUI Behavior

- The app opens to a single-window PySide6 UI titled `TIFF Spot White`.
- Users can choose one image or drag/drop one local file onto the preview area.
- The preview renders CMYK through Pillow to RGB and composites over white using alpha.
- The spot overlay preview tints detected spot pixels magenta.
- The convert button is disabled until a file loads successfully.
- If the output path already exists, the GUI asks before overwriting.
- If the input already has a channel named `white`, the GUI prompts for cancel, overwrite, or save as `white 2`.
- Conversion runs on a `QThread` so the GUI does not block.

## Commands

Create a local editable install with tests:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[test]"
```

Run tests:

```bash
.venv/bin/python -m pytest
```

Run the GUI:

```bash
.venv/bin/python -m tiff_spot_white.gui
```

Run entrypoint checks:

```bash
.venv/bin/python -m tiff_spot_white --version
.venv/bin/python -m tiff_spot_white --self-test
```

Build macOS from macOS:

```bash
scripts/build_macos.sh
```

Build Windows from Windows:

```powershell
.\scripts\build_windows.ps1
```

## Test Fixtures

- `tests/images/test1.tiff`: real CMYK TIFF fixture used for preservation tests when present.
- `tests/images/test1_photoshop.tif`: Photoshop reference fixture used to compare spot metadata resource payloads.
- `tests/images/test2.png`: PNG fallback fixture used to confirm non-CMYK conversion warnings.
- Tests skip fixture-dependent checks if these files are missing.

## Generated And Local Artifacts

- `dist/`, `build/`, `.venv/`, `.pytest_cache/`, and `__pycache__/` are generated/local artifacts.
- Build scripts may install dependencies into the active Python environment.
- macOS builds produce both `dist/Tiff Spot White/Tiff Spot White` for smoke tests and `dist/Tiff Spot White.app` for user launch.
- Windows builds produce onefile executable `dist/Tiff Spot White.exe`.
- The release workflow copies the Windows executable to `dist/tiff-spot-white-windows.exe` before uploading it.

## Practical Development Notes

- Keep changes tightly scoped. The core image contract is more important than broad refactoring.
- Prefer adding or updating focused tests in `tests/test_core.py` for conversion behavior and metadata changes.
- For GUI-only helper changes, `tests/test_gui.py` is intentionally lightweight and does not launch the full Qt app.
- If changing PyInstaller packaging, verify both the script path and the bundled `--self-test` path because CI depends on them.
- If validating actual Photoshop/RIP interpretation, code-level validation is not enough; the README already notes final recognition depends on consuming software.
