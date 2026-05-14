"""Executable entrypoint for the TIFF Spot White app."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
import tifffile

from . import __version__
from .core import convert_image, decode_photoshop_spot_channel, generate_spot_mask, load_image


def self_test() -> list[str]:
    checks: list[str] = []
    with tempfile.TemporaryDirectory(prefix="tiff-spot-white-") as tmp:
        workdir = Path(tmp)
        source = workdir / "selftest.tiff"
        output = workdir / "selftest_spotwhite.tiff"
        data = np.zeros((2, 3, 5), dtype=np.uint8)
        data[..., :4] = 9
        data[0, 0, :4] = 0
        data[0, 1, :4] = 0
        data[..., 4] = 255
        data[0, 1, 4] = 0
        tifffile.imwrite(
            source,
            data,
            photometric="separated",
            planarconfig="contig",
            extrasamples=["unassalpha"],
            compression=None,
            metadata=None,
        )

        loaded = load_image(source)
        expected = generate_spot_mask(loaded.cmyk, loaded.alpha)
        result = convert_image(source, output)
        checks.extend(result.validation)

        with tifffile.TiffFile(output) as tif:
            page = tif.pages[0]
            converted = page.asarray()
            if converted.shape != (2, 3, 6):
                raise RuntimeError(f"Unexpected output shape: {converted.shape}")
            if not np.array_equal(converted[..., :4], data[..., :4]):
                raise RuntimeError("CMYK preservation check failed.")
            if not np.array_equal(converted[..., 4], data[..., 4]):
                raise RuntimeError("Alpha preservation check failed.")
            if not np.array_equal(decode_photoshop_spot_channel(converted[..., -1]), expected):
                raise RuntimeError("Spot mask check failed.")
            if int(page.tags["Compression"].value) != 1:
                raise RuntimeError("Output is not uncompressed.")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TIFF Spot White desktop app")
    parser.add_argument("--version", action="store_true", help="print the app version and exit")
    parser.add_argument("--self-test", action="store_true", help="run a bundled conversion smoke test and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    if args.self_test:
        checks = self_test()
        print("Self-test passed.")
        for check in checks:
            print(f"- {check}")
        return 0

    from .gui import main as gui_main

    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
