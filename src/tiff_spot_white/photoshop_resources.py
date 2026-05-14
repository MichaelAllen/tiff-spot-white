"""Small Photoshop Image Resource Block helpers.

Photoshop-compatible TIFF spot channels rely on private ImageResources in TIFF
tag 34377. The structures here intentionally cover only the resources needed to
name and identify extra channels as alpha/spot channels.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


RESOURCE_ALPHA_NAMES = 1006
RESOURCE_DISPLAY_INFO = 1007
RESOURCE_UNICODE_ALPHA_NAMES = 1045
RESOURCE_ALPHA_IDENTIFIERS = 1053
RESOURCE_ALTERNATE_SPOT_COLORS = 1067
RESOURCE_DISPLAY_INFO_FLOAT = 1077


@dataclass(frozen=True)
class ImageResourceBlock:
    resource_id: int
    data: bytes
    name: str = ""
    signature: bytes = b"8BIM"


def _pascal(value: str, pad_to: int = 2) -> bytes:
    encoded = value.encode("macroman", errors="replace")[:255]
    data = bytes([len(encoded)]) + encoded
    while len(data) % pad_to:
        data += b"\0"
    return data


def _pascal_unpadded(value: str) -> bytes:
    encoded = value.encode("macroman", errors="replace")[:255]
    return bytes([len(encoded)]) + encoded


def pack_resource_block(block: ImageResourceBlock) -> bytes:
    name = _pascal(block.name)
    payload = block.data
    padded = payload + (b"\0" if len(payload) % 2 else b"")
    return block.signature + struct.pack(">H", block.resource_id) + name + struct.pack(">I", len(payload)) + padded


def parse_resource_blocks(data: bytes | None) -> list[ImageResourceBlock]:
    if not data:
        return []
    blocks: list[ImageResourceBlock] = []
    offset = 0
    size = len(data)
    while offset + 12 <= size:
        signature = data[offset : offset + 4]
        if signature not in {b"8BIM", b"8B64"}:
            break
        resource_id = struct.unpack(">H", data[offset + 4 : offset + 6])[0]
        offset += 6
        name_len = data[offset]
        name_start = offset + 1
        name_end = name_start + name_len
        name = data[name_start:name_end].decode("macroman", errors="replace")
        offset = name_end
        if (1 + name_len) % 2:
            offset += 1
        if offset + 4 > size:
            break
        payload_len = struct.unpack(">I", data[offset : offset + 4])[0]
        offset += 4
        payload = data[offset : offset + payload_len]
        blocks.append(ImageResourceBlock(resource_id, payload, name, signature))
        offset += payload_len + (payload_len % 2)
    return blocks


def pack_alpha_names(names: list[str]) -> bytes:
    return b"".join(_pascal_unpadded(name) for name in names)


def parse_alpha_names(data: bytes | None) -> list[str]:
    names: list[str] = []
    if not data:
        return names
    offset = 0
    while offset < len(data):
        size = data[offset]
        offset += 1
        if offset + size > len(data):
            break
        if size:
            names.append(data[offset : offset + size].decode("macroman", errors="replace"))
        offset += size
    return names


def pack_unicode_alpha_names(names: list[str]) -> bytes:
    data = bytearray()
    for name in names:
        encoded = name.encode("utf-16be") + b"\0\0"
        data.extend(struct.pack(">I", len(name) + 1))
        data.extend(encoded)
    return bytes(data)


def pack_alpha_identifiers(ids: list[int]) -> bytes:
    return b"".join(struct.pack(">i", value) for value in ids)


def parse_alpha_identifiers(data: bytes | None) -> list[int]:
    if not data:
        return []
    ids: list[int] = []
    for offset in range(0, len(data) - 3, 4):
        ids.append(struct.unpack(">i", data[offset : offset + 4])[0])
    return ids


def pack_display_info_float(channel_kinds: list[int], spot_index: int, solidity_percent: int = 50) -> bytes:
    records = [struct.pack(">I", 1)]
    for index, kind in enumerate(channel_kinds):
        if index == spot_index:
            # Photoshop's DisplayInfo resource stores CMYK components inverted:
            # 0% C, 100% M, 0% Y, 0% K becomes ffff, 0000, ffff, ffff.
            color = (2, 65535, 0, 65535, 65535)
            opacity = max(0, min(100, solidity_percent))
        else:
            color = (0, 65535, 0, 0, 0)
            opacity = 100
        records.append(struct.pack(">H4HHB", *color, opacity, kind))
    return b"".join(records)


def pack_alternate_spot_colors(channel_id: int) -> bytes:
    # Version 1, one channel. Photoshop writes 100% Magenta alternate spot
    # color as Lab (space 7) with these 16-bit components.
    return struct.pack(">HHI H4H", 1, 1, channel_id, 7, 0x1455, 0x1F7C, 0xFD3F, 0)


def merge_spot_resources(
    existing: bytes | None,
    extra_names: list[str],
    spot_name: str,
) -> bytes:
    preserved = [
        block
        for block in parse_resource_blocks(existing)
        if block.resource_id
        not in {
            RESOURCE_ALPHA_NAMES,
            RESOURCE_DISPLAY_INFO,
            RESOURCE_UNICODE_ALPHA_NAMES,
            RESOURCE_ALPHA_IDENTIFIERS,
            RESOURCE_ALTERNATE_SPOT_COLORS,
            RESOURCE_DISPLAY_INFO_FLOAT,
        }
    ]
    spot_index = extra_names.index(spot_name)
    identifiers = [0] + list(range(3, len(extra_names) + 2))
    channel_kinds = [1] * len(extra_names)
    channel_kinds[spot_index] = 2
    spot_identifier = identifiers[spot_index]
    blocks = preserved + [
        ImageResourceBlock(RESOURCE_ALPHA_NAMES, pack_alpha_names(extra_names)),
        ImageResourceBlock(RESOURCE_UNICODE_ALPHA_NAMES, pack_unicode_alpha_names(extra_names)),
        ImageResourceBlock(RESOURCE_DISPLAY_INFO_FLOAT, pack_display_info_float(channel_kinds, spot_index)),
        ImageResourceBlock(RESOURCE_ALPHA_IDENTIFIERS, pack_alpha_identifiers(identifiers)),
        ImageResourceBlock(RESOURCE_ALTERNATE_SPOT_COLORS, pack_alternate_spot_colors(spot_identifier)),
    ]
    return b"".join(pack_resource_block(block) for block in blocks)


def resource_payload(resources: bytes | None, resource_id: int) -> bytes | None:
    for block in parse_resource_blocks(resources):
        if block.resource_id == resource_id:
            return block.data
    return None
