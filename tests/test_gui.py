from __future__ import annotations

from tiff_spot_white.gui import image_file_filter, supported_image_extensions


def test_supported_image_extensions_include_tiff_and_png() -> None:
    extensions = supported_image_extensions()

    assert ".tif" in extensions
    assert ".tiff" in extensions
    assert ".png" in extensions


def test_image_file_filter_advertises_supported_images() -> None:
    file_filter = image_file_filter()

    assert file_filter.startswith("Supported images (")
    assert "*.png" in file_filter
    assert "*.tiff" in file_filter
    assert "All files (*)" in file_filter
