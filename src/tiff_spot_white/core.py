"""Core TIFF conversion and validation logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import tifffile
from PIL import Image

from .photoshop_resources import (
    RESOURCE_ALPHA_IDENTIFIERS,
    RESOURCE_ALPHA_NAMES,
    RESOURCE_ALTERNATE_SPOT_COLORS,
    RESOURCE_DISPLAY_INFO_FLOAT,
    RESOURCE_UNICODE_ALPHA_NAMES,
    merge_spot_resources,
    parse_alpha_names,
    parse_resource_blocks,
    resource_payload,
)

ExistingSpotAction = Literal["cancel", "overwrite", "alternate"]


@dataclass
class LoadedImage:
    path: Path
    cmyk: np.ndarray
    alpha: np.ndarray
    extras: list[np.ndarray] = field(default_factory=list)
    extra_names: list[str] = field(default_factory=list)
    metadata_tags: dict[int, object] = field(default_factory=dict)
    image_resources: bytes | None = None
    resolution: tuple[float, float] | None = None
    resolution_unit: int | None = None
    icc_profile: bytes | None = None
    description: str | None = None
    xmp: bytes | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def shape(self) -> tuple[int, int]:
        return self.cmyk.shape[:2]


@dataclass
class ConversionResult:
    output_path: Path
    spot_name: str
    warnings: list[str]
    validation: list[str]


def default_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}_spotwhite.tiff")


def generate_spot_mask(cmyk: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    if cmyk.ndim != 3 or cmyk.shape[-1] != 4:
        raise ValueError("CMYK data must have shape height x width x 4.")
    if alpha.shape != cmyk.shape[:2]:
        raise ValueError("Alpha channel shape must match CMYK dimensions.")
    exact_white = np.all(cmyk == 0, axis=-1)
    return np.where(exact_white & (alpha > 0), alpha, 0).astype(np.uint8)


def encode_photoshop_spot_channel(logical_spot: np.ndarray) -> np.ndarray:
    """Encode logical ink coverage for Photoshop/RIP spot channel polarity.

    The app's logical mask uses 255 as full white-ink coverage. Photoshop spot
    channels in TIFF are stored with inverse polarity: 0 is full spot ink and
    255 is no spot ink.
    """

    return (255 - logical_spot).astype(np.uint8)


def decode_photoshop_spot_channel(stored_spot: np.ndarray) -> np.ndarray:
    return (255 - stored_spot).astype(np.uint8)


def detect_existing_spot_names(image_resources: bytes | None) -> list[str]:
    return parse_alpha_names(resource_payload(image_resources, RESOURCE_ALPHA_NAMES))


def _tag_value(page: tifffile.TiffPage, code: int):
    tag = page.tags.get(code)
    return tag.value if tag is not None else None


def _read_resolution(page: tifffile.TiffPage) -> tuple[tuple[float, float] | None, int | None]:
    xres = _tag_value(page, 282)
    yres = _tag_value(page, 283)
    unit = _tag_value(page, 296)
    if xres and yres:
        return (float(xres[0] / xres[1]), float(yres[0] / yres[1])), int(unit or 2)
    return None, int(unit) if unit else None


def _pillow_resolution(image: Image.Image) -> tuple[tuple[float, float] | None, int | None]:
    dpi = image.info.get("dpi")
    if isinstance(dpi, tuple) and len(dpi) >= 2 and dpi[0] and dpi[1]:
        return (float(dpi[0]), float(dpi[1])), 2
    return None, None


def load_image(path: Path) -> LoadedImage:
    warnings: list[str] = []
    path = Path(path)
    resolution: tuple[float, float] | None = None
    resolution_unit: int | None = None
    try:
        with tifffile.TiffFile(path) as tif:
            if len(tif.pages) > 1:
                warnings.append("Input is a multi-page TIFF. Only the first page will be processed.")
            page = tif.pages[0]
            arr = page.asarray()
            photometric = page.photometric.name if page.photometric else ""
            samples = arr.shape[-1] if arr.ndim == 3 else 1
            resources = _tag_value(page, 34377)
            if isinstance(resources, str):
                resources = resources.encode("latin1")
            resolution, resolution_unit = _read_resolution(page)
            icc = _tag_value(page, 34675)
            xmp = _tag_value(page, 700)
            description = _tag_value(page, 270)
            extra_names = detect_existing_spot_names(resources)
            if photometric == "SEPARATED" and samples >= 4:
                cmyk = np.asarray(arr[..., :4], dtype=np.uint8)
                extras_data = [np.asarray(arr[..., i], dtype=np.uint8) for i in range(4, samples)]
                alpha = extras_data[0] if extras_data else np.full(cmyk.shape[:2], 255, dtype=np.uint8)
                extras = extras_data[1:] if extras_data else []
                if not extras_data:
                    warnings.append("Input has no alpha channel. Full opacity alpha will be used.")
                while len(extra_names) < len(extras_data):
                    extra_names.append("Alpha" if len(extra_names) == 0 else f"Alpha {len(extra_names) + 1}")
                return LoadedImage(
                    path=path,
                    cmyk=cmyk,
                    alpha=alpha.copy(),
                    extras=extras,
                    extra_names=extra_names,
                    image_resources=resources,
                    resolution=resolution,
                    resolution_unit=resolution_unit,
                    icc_profile=bytes(icc) if icc else None,
                    description=description if isinstance(description, str) else None,
                    xmp=bytes(xmp) if xmp else None,
                    warnings=warnings,
                )
            warnings.append("Input is not CMYK. It will be converted to CMYK; original color values cannot be preserved exactly.")
    except Exception as exc:
        warnings.append(f"TIFF CMYK read failed ({exc}). Falling back to Pillow conversion.")
        warnings.append("Input is not CMYK. It will be converted to CMYK; original color values cannot be preserved exactly.")

    with Image.open(path) as image:
        if getattr(image, "n_frames", 1) > 1:
            warnings.append("Input is a multi-page image. Only the first page will be processed.")
        image.seek(0)
        if resolution is None:
            resolution, resolution_unit = _pillow_resolution(image)
        alpha_image = image.getchannel("A") if "A" in image.getbands() else None
        if alpha_image is None:
            warnings.append("Input has no alpha channel. Full opacity alpha will be used.")
            alpha = np.full((image.height, image.width), 255, dtype=np.uint8)
        else:
            alpha = np.asarray(alpha_image, dtype=np.uint8)
        cmyk = np.asarray(image.convert("CMYK"), dtype=np.uint8)
    return LoadedImage(
        path=path,
        cmyk=cmyk,
        alpha=alpha,
        resolution=resolution,
        resolution_unit=resolution_unit,
        warnings=warnings,
    )


def _ink_names(names: list[str]) -> bytes:
    # TIFF InkNames is NUL-separated and terminated.
    return b"\0".join(name.encode("ascii", errors="replace") for name in names) + b"\0"


def _extratags(image: LoadedImage, output_resources: bytes, ink_names: list[str]):
    tags = [
        (34377, "B", len(output_resources), output_resources, True),
        (332, "H", 1, 1, False),
        (334, "H", 1, len(ink_names), False),
        (333, "s", len(_ink_names(ink_names)), _ink_names(ink_names), False),
    ]
    if image.xmp:
        tags.append((700, "B", len(image.xmp), image.xmp, True))
    return tags


def convert_image(
    input_path: Path,
    output_path: Path | None = None,
    existing_spot_action: ExistingSpotAction = "cancel",
) -> ConversionResult:
    image = load_image(input_path)
    warnings = list(image.warnings)
    output = Path(output_path) if output_path else default_output_path(Path(input_path))
    existing_names = [name.lower() for name in image.extra_names]
    spot_name = "white"
    if "white" in existing_names:
        if existing_spot_action == "cancel":
            raise ValueError('Input already contains a channel named "white".')
        if existing_spot_action == "alternate":
            spot_name = "white 2"
        elif existing_spot_action == "overwrite":
            index = existing_names.index("white")
            if index == 0:
                raise ValueError('Cannot overwrite "white" because it appears to be the preserved alpha channel.')
            image.extras.pop(index - 1)
            image.extra_names.pop(index)
        else:
            raise ValueError(f"Unsupported existing spot action: {existing_spot_action}")

    spot = generate_spot_mask(image.cmyk, image.alpha)
    stored_spot = encode_photoshop_spot_channel(spot)
    extra_names = list(image.extra_names)
    if not extra_names:
        extra_names.append("Alpha")
    extra_names.append(spot_name)
    output_resources = merge_spot_resources(image.image_resources, extra_names, spot_name)
    channels = [image.cmyk, image.alpha[..., None]]
    channels.extend(extra[..., None] for extra in image.extras)
    channels.append(stored_spot[..., None])
    data = np.concatenate(channels, axis=-1)
    extrasamples = ["unassalpha"] + ["unspecified"] * (data.shape[-1] - 5)
    ink_names = ["Cyan", "Magenta", "Yellow", "Black", *extra_names]

    tifffile.imwrite(
        output,
        data,
        photometric="separated",
        planarconfig="contig",
        extrasamples=extrasamples,
        compression=None,
        metadata=None,
        iccprofile=image.icc_profile,
        description=image.description,
        resolution=image.resolution,
        resolutionunit=image.resolution_unit,
        extratags=_extratags(image, output_resources, ink_names),
    )
    validation = validate_output(image, output, spot, spot_name)
    if not any("Photoshop spot metadata present" in item for item in validation):
        warnings.append("Could not confidently verify Photoshop-compatible spot metadata. Confirm in Photoshop or RIP software.")
    return ConversionResult(output, spot_name, warnings, validation)


def validate_output(source: LoadedImage, output_path: Path, expected_spot: np.ndarray, spot_name: str) -> list[str]:
    checks: list[str] = []
    if not output_path.exists():
        return ["Output file was not created."]
    checks.append("Output file exists.")
    with tifffile.TiffFile(output_path) as tif:
        page = tif.pages[0]
        arr = page.asarray()
        if arr.shape[:2] == source.shape:
            checks.append("Dimensions match input first page.")
        if np.array_equal(arr[..., :4], source.cmyk):
            checks.append("CMYK data preserved.")
        if np.array_equal(arr[..., 4], source.alpha):
            checks.append("Alpha channel preserved.")
        if np.array_equal(decode_photoshop_spot_channel(arr[..., -1]), expected_spot):
            checks.append("Spot mask matches expected detection logic using Photoshop spot-channel polarity.")
        compression = page.tags.get("Compression")
        if compression is not None and int(compression.value) == 1:
            checks.append("Output TIFF is uncompressed.")
        resources = _tag_value(page, 34377)
        block_ids = {block.resource_id for block in parse_resource_blocks(resources)}
        names = parse_alpha_names(resource_payload(resources, RESOURCE_ALPHA_NAMES))
        required = {
            RESOURCE_ALPHA_NAMES,
            RESOURCE_UNICODE_ALPHA_NAMES,
            RESOURCE_DISPLAY_INFO_FLOAT,
            RESOURCE_ALPHA_IDENTIFIERS,
            RESOURCE_ALTERNATE_SPOT_COLORS,
        }
        if spot_name in names and required.issubset(block_ids):
            checks.append("Photoshop spot metadata present.")
    return checks
