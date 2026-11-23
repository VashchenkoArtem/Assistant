import base64
import binascii
import re
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

_EMBEDDED_PNG = re.compile(r"data:image/png;base64,([^\"']+)")


def icon_path(name: str) -> Path:
    assets = Path(__file__).parent / "assets"
    relative_name = Path(name)
    png_path = assets / "png" / relative_name.with_suffix(".png")
    if png_path.is_file():
        return png_path
    png_path = assets / "png" / f"{relative_name.stem}.png"
    if png_path.is_file():
        return png_path
    return assets / "icons" / name


@lru_cache(maxsize=256)
def load_pixmap(path: str | Path, size: int) -> QPixmap:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Icon asset not found: {path}")

    if path.suffix.lower() == ".svg":
        pixmap = _render_svg(path, size)
    else:
        pixmap = QPixmap(str(path))

    pixmap = _trim_transparency(pixmap)
    if pixmap.isNull():
        raise ValueError(f"Icon asset contains no visible image: {path}")
    return pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _render_svg(path: Path, size: int) -> QPixmap:
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        raise ValueError(f"Invalid SVG icon asset: {path}")

    canvas_size = max(size * 4, 64)
    image = QImage(canvas_size, canvas_size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()

    pixmap = _trim_transparency(QPixmap.fromImage(image))
    if not pixmap.isNull():
        return pixmap

    svg_root = ET.parse(path).getroot()
    for element in svg_root.iter():
        for value in element.attrib.values():
            match = _EMBEDDED_PNG.fullmatch(value)
            if match is None:
                continue
            try:
                image_data = base64.b64decode(match.group(1), validate=True)
            except binascii.Error as error:
                raise ValueError(f"Invalid embedded PNG in SVG icon: {path}") from error
            pixmap = QPixmap()
            if not pixmap.loadFromData(image_data, "PNG"):
                raise ValueError(f"Invalid embedded PNG in SVG icon: {path}")
            return pixmap

    return QPixmap()


def _trim_transparency(pixmap: QPixmap) -> QPixmap:
    if pixmap.isNull():
        return QPixmap()

    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    data = image.constBits()
    data.setsize(image.sizeInBytes())
    pixels = memoryview(data)
    width, height = image.width(), image.height()
    left, top, right, bottom = width, height, -1, -1
    bytes_per_row = image.bytesPerLine()
    for y in range(height):
        row = y * bytes_per_row
        for x in range(width):
            if pixels[row + x * 4 + 3] >= 24:
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)

    if right < left or bottom < top:
        return QPixmap()
    return QPixmap.fromImage(image.copy(left, top, right - left + 1, bottom - top + 1))
