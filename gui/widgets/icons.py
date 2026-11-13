from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QImage, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer


ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


def icon_path(name: str) -> Path:
    png_path = ASSETS_DIR / "png" / f"{Path(name).stem}.png"
    if png_path.exists():
        return png_path
    return ASSETS_DIR / name


def make_pixmap(name: str, size: int) -> QPixmap:
    path = icon_path(name)
    if path.suffix.lower() == ".svg":
        renderer = QSvgRenderer(str(path))
        if not renderer.isValid():
            return QPixmap()
        canvas_size = max(size * 4, 64)
        image = QImage(canvas_size, canvas_size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        pixmap = QPixmap.fromImage(image)
    else:
        pixmap = QPixmap(str(path))

    if pixmap.isNull():
        return QPixmap()

    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    left, top, right, bottom = image.width(), image.height(), -1, -1
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() >= 24:
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)

    if right >= left and bottom >= top:
        pixmap = QPixmap.fromImage(
            image.copy(left, top, right - left + 1, bottom - top + 1)
        )

    return pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def make_icon(name: str, size: int = 20) -> QIcon:
    return QIcon(make_pixmap(name, size))
