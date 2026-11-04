"""Facts about images that need no AI: the brand's image info file, size, and see-through pixels."""

import base64
import io
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image as PilImage

VISION_MAX_SIDE = 512
"""Images are shrunk to this before the vision model sees them; it reads them at low detail anyway."""

_SVG_SIZE = re.compile(r'<svg[^>]*\bwidth="(\d+(?:\.\d+)?)[a-z]*"[^>]*\bheight="(\d+(?:\.\d+)?)', re.IGNORECASE)
_SVG_VIEWBOX = re.compile(r'viewBox="[\d.\-]+ [\d.\-]+ ([\d.]+) ([\d.]+)"', re.IGNORECASE)


def records_by_image(data_files: list[tuple[str, bytes]], image_paths: list[str]) -> dict[str, dict[str, Any]]:
    """Finds image info files among the brand's data files and matches each row to an image.

    A data file counts when it is JSON holding a list of objects, and one field of those objects
    names image files: a file name, a path, or a name without its extension.
    """
    by_name = {PurePosixPath(path).name.lower(): path for path in image_paths}
    by_stem = {PurePosixPath(path).stem.lower(): path for path in image_paths}
    matched: dict[str, dict[str, Any]] = {}
    for _, content in data_files:
        for row in _rows(content):
            path = _match(row, by_name, by_stem)
            if path and path not in matched:
                matched[path] = row
    return matched


def measure(path: Path) -> tuple[int, int, bool]:
    """Width, height, and whether any pixel is see-through. A file that can't be read gives (0, 0, False)."""
    if path.suffix.lower() == ".svg":
        return (*_svg_size(path.read_text(errors="replace")), True)
    try:
        with PilImage.open(path) as image:
            width, height = image.size
            if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                alpha = image.convert("RGBA").getchannel("A")
                return width, height, alpha.getextrema()[0] < 255
            return width, height, False
    except (OSError, ValueError):
        return 0, 0, False


def vision_data_url(path: Path) -> str | None:
    """A small JPEG of the image as a data URL, or None when the vision model can't read it (SVG, broken files)."""
    if path.suffix.lower() == ".svg":
        return None
    try:
        with PilImage.open(path) as image:
            rgba = image.convert("RGBA")
    except (OSError, ValueError):
        return None
    rgba.thumbnail((VISION_MAX_SIDE, VISION_MAX_SIDE))
    flat = PilImage.new("RGB", rgba.size, "white")
    flat.paste(rgba, mask=rgba.getchannel("A"))
    buffer = io.BytesIO()
    flat.save(buffer, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def _rows(content: bytes) -> list[dict[str, Any]]:
    try:
        data = json.loads(content)
    except ValueError:
        return []
    if isinstance(data, dict):
        lists = [value for value in data.values() if isinstance(value, list)]
        data = lists[0] if len(lists) == 1 else []
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _match(row: dict[str, Any], by_name: dict[str, str], by_stem: dict[str, str]) -> str | None:
    for value in row.values():
        if not isinstance(value, str) or not value:
            continue
        name = PurePosixPath(value.replace("\\", "/")).name.lower()
        if name in by_name:
            return by_name[name]
    for value in row.values():
        if isinstance(value, str) and value.lower() in by_stem:
            return by_stem[value.lower()]
    return None


def _svg_size(text: str) -> tuple[int, int]:
    match = _SVG_SIZE.search(text) or _SVG_VIEWBOX.search(text)
    return (round(float(match.group(1))), round(float(match.group(2)))) if match else (0, 0)
