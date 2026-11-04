from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout


# ============================ КАРТКА ПОВІДОМЛЕННЯ ЧАТУ ============================
class ChatCard(QFrame):
    """A message card used as a visual placeholder in the prototype."""

    # Завантаження і впорядкування SVG/PNG-іконок усередині картки.
    @staticmethod
    def load_pixmap(path: str, size: int) -> QPixmap:
        if path.lower().endswith(".svg"):
            renderer = QSvgRenderer(path)
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
            pixmap = QPixmap(path)

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
            pixmap = QPixmap.fromImage(image.copy(left, top, right - left + 1, bottom - top + 1))

        return pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

    def __init__(
        self,
        author: str,
        body: str,
        time: str,
        icon: str,
        is_user: bool = False,
        status: str | None = None,
        status_icon: str | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("userCard" if is_user else "assistantCard")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(12)

        # Ліва частина картки: аватар асистента або користувача.
        icon_label = QLabel()
        icon_label.setObjectName("cardIcon")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(28, 28)
        if icon.lower().endswith((".svg", ".png")):
            icon_label.setPixmap(self.load_pixmap(icon, 20))
        else:
            icon_label.setText(icon)
        layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)

        # Права частина картки: заголовок, текст і час.
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        author_label = QLabel(author)
        author_label.setObjectName("messageAuthor")
        header_layout.addWidget(author_label)
        header_layout.addStretch()

        # Необов'язковий рядок статусу праворуч у заголовку картки.
        if status:
            if status_icon:
                status_icon_label = QLabel()
                status_icon_label.setFixedSize(16, 16)
                status_icon_label.setPixmap(self.load_pixmap(status_icon, 14))
                header_layout.addWidget(status_icon_label)

            status_label = QLabel(status)
            status_label.setObjectName("messageStatus")
            status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            header_layout.addWidget(status_label)

        text_layout.addLayout(header_layout)

        body_label = QLabel(body)
        body_label.setObjectName("messageBody")
        body_label.setWordWrap(True)
        text_layout.addWidget(body_label)

        time_label = QLabel(time)
        time_label.setObjectName("messageTime")
        text_layout.addWidget(time_label)

        layout.addLayout(text_layout, 1)
