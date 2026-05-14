from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import tifffile

from tiff_spot_white.core import (
    convert_image,
    decode_photoshop_spot_channel,
    default_output_path,
    detect_existing_spot_names,
    encode_photoshop_spot_channel,
    generate_spot_mask,
    load_image,
)
from tiff_spot_white.photoshop_resources import (
    RESOURCE_ALPHA_NAMES,
    ImageResourceBlock,
    pack_alpha_names,
    pack_resource_block,
    resource_payload,
)


def make_cmyka(path: Path, data: np.ndarray) -> None:
    tifffile.imwrite(
        path,
        data,
        photometric="separated",
        planarconfig="contig",
        extrasamples=["unassalpha"] + ["unspecified"] * max(0, data.shape[-1] - 5),
        compression=None,
        metadata=None,
    )


def test_generate_spot_mask_exact_white_and_alpha() -> None:
    cmyk = np.array(
        [
            [[0, 0, 0, 0], [1, 0, 0, 0]],
            [[0, 0, 0, 0], [0, 0, 0, 1]],
        ],
        dtype=np.uint8,
    )
    alpha = np.array([[255, 255], [0, 128]], dtype=np.uint8)
    assert generate_spot_mask(cmyk, alpha).tolist() == [[255, 0], [0, 0]]


def test_photoshop_spot_channel_uses_inverse_storage_polarity() -> None:
    logical = np.array([[255, 128, 0]], dtype=np.uint8)

    stored = encode_photoshop_spot_channel(logical)

    assert stored.tolist() == [[0, 127, 255]]
    np.testing.assert_array_equal(decode_photoshop_spot_channel(stored), logical)


def test_default_output_path() -> None:
    assert default_output_path(Path("/tmp/file.tiff")) == Path("/tmp/file_spotwhite.tiff")


def test_convert_preserves_cmyk_alpha_and_spot_values(tmp_path: Path) -> None:
    source = tmp_path / "art.tiff"
    data = np.zeros((2, 3, 5), dtype=np.uint8)
    data[..., :4] = 7
    data[0, 0, :4] = 0
    data[0, 1, :4] = 0
    data[1, 0, :4] = [0, 0, 0, 1]
    data[..., 4] = 255
    data[0, 1, 4] = 0
    data[1, 1, 4] = 128
    make_cmyka(source, data)

    result = convert_image(source)

    with tifffile.TiffFile(result.output_path) as tif:
        out = tif.pages[0].asarray()
        assert out.shape == (2, 3, 6)
        np.testing.assert_array_equal(out[..., :4], data[..., :4])
        np.testing.assert_array_equal(out[..., 4], data[..., 4])
        assert out[..., 5].tolist() == [[0, 255, 255], [255, 255, 255]]
        assert decode_photoshop_spot_channel(out[..., 5]).tolist() == [[255, 0, 0], [0, 0, 0]]
        assert "Photoshop spot metadata present." in result.validation


def test_first_page_only_warning(tmp_path: Path) -> None:
    source = tmp_path / "multi.tiff"
    page1 = np.zeros((2, 2, 5), dtype=np.uint8)
    page1[..., 4] = 255
    page2 = np.ones((4, 4, 5), dtype=np.uint8)
    with tifffile.TiffWriter(source) as tif:
        tif.write(page1, photometric="separated", planarconfig="contig", extrasamples=["unassalpha"], metadata=None)
        tif.write(page2, photometric="separated", planarconfig="contig", extrasamples=["unassalpha"], metadata=None)

    loaded = load_image(source)

    assert loaded.shape == (2, 2)
    assert any("multi-page" in warning for warning in loaded.warnings)


def test_existing_spot_name_detection() -> None:
    resources = pack_resource_block(ImageResourceBlock(RESOURCE_ALPHA_NAMES, pack_alpha_names(["Alpha", "white"])))

    assert detect_existing_spot_names(resources) == ["Alpha", "white"]
    assert resource_payload(resources, RESOURCE_ALPHA_NAMES) is not None


def test_existing_white_cancel_and_alternate(tmp_path: Path) -> None:
    source = tmp_path / "existing.tiff"
    data = np.zeros((2, 2, 6), dtype=np.uint8)
    data[..., 4] = 255
    resources = pack_resource_block(ImageResourceBlock(RESOURCE_ALPHA_NAMES, pack_alpha_names(["Alpha", "white"])))
    tifffile.imwrite(
        source,
        data,
        photometric="separated",
        planarconfig="contig",
        extrasamples=["unassalpha", "unspecified"],
        compression=None,
        metadata=None,
        extratags=[(34377, "B", len(resources), resources, True)],
    )

    with pytest.raises(ValueError):
        convert_image(source)
    result = convert_image(source, tmp_path / "alternate.tiff", existing_spot_action="alternate")
    assert result.spot_name == "white 2"


def test_non_cmyk_conversion_warning(tmp_path: Path) -> None:
    from PIL import Image

    source = tmp_path / "rgb.tiff"
    Image.new("RGBA", (2, 2), (255, 255, 255, 128)).save(source)

    loaded = load_image(source)

    assert loaded.cmyk.shape == (2, 2, 4)
    assert any("not CMYK" in warning for warning in loaded.warnings)


def test_real_cmyk_fixture_conversion_preserves_data_and_metadata(tmp_path: Path) -> None:
    source = Path("tests/images/test1.tiff")
    if not source.exists():
        pytest.skip("real TIFF fixture is not available")
    loaded = load_image(source)
    expected_spot = generate_spot_mask(loaded.cmyk, loaded.alpha)

    result = convert_image(source, tmp_path / "test1_spotwhite.tiff")

    assert result.warnings == []
    assert "Photoshop spot metadata present." in result.validation
    with tifffile.TiffFile(result.output_path) as tif:
        page = tif.pages[0]
        out = page.asarray()
        np.testing.assert_array_equal(out[..., :4], loaded.cmyk)
        np.testing.assert_array_equal(out[..., 4], loaded.alpha)
        np.testing.assert_array_equal(decode_photoshop_spot_channel(out[..., -1]), expected_spot)
        assert int(page.tags["Compression"].value) == 1
        assert page.tags.get(34675) is not None
        assert page.tags.get(700) is not None


def test_real_cmyk_fixture_spot_color_metadata_matches_photoshop_reference(tmp_path: Path) -> None:
    source = Path("tests/images/test1.tiff")
    photoshop_reference = Path("tests/images/test1_photoshop.tif")
    if not source.exists() or not photoshop_reference.exists():
        pytest.skip("real Photoshop reference fixture is not available")

    result = convert_image(source, tmp_path / "test1_spotwhite.tiff")

    with tifffile.TiffFile(result.output_path) as actual_tif, tifffile.TiffFile(photoshop_reference) as reference_tif:
        actual_resources = actual_tif.pages[0].tags[34377].value
        reference_resources = reference_tif.pages[0].tags[34377].value
        assert resource_payload(actual_resources, 1053) == resource_payload(reference_resources, 1053)
        assert resource_payload(actual_resources, 1067) == resource_payload(reference_resources, 1067)
        assert resource_payload(actual_resources, 1077) == resource_payload(reference_resources, 1077)


def test_real_png_fixture_core_fallback_warns_not_cmyk() -> None:
    source = Path("tests/images/test2.png")
    if not source.exists():
        pytest.skip("real PNG fixture is not available")

    loaded = load_image(source)

    assert loaded.cmyk.shape[:2] == loaded.alpha.shape
    assert loaded.cmyk.shape[-1] == 4
    assert any("not CMYK" in warning for warning in loaded.warnings)
