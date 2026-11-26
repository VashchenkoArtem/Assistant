from PyQt6.QtGui import QIcon, QPixmap

from ...icon_loader import icon_path, load_pixmap


def make_pixmap(name: str, size: int) -> QPixmap:
    return load_pixmap(icon_path(name), size)


def make_icon(name: str, size: int = 20) -> QIcon:
    return QIcon(make_pixmap(name, size))
