import math

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ...icon_loader import load_pixmap


class LoadingDot(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(45)

    def _advance(self) -> None:
        self._phase = (self._phase + 0.12) % (2 * math.pi)
        self.update()

    def paintEvent(self, _event) -> None:
        pulse = (math.sin(self._phase) + 1) / 2
        radius = 3.0 + pulse
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(112, 132, 255, round(110 + 145 * pulse)))
        painter.drawEllipse(
            QRectF(
                (self.width() - radius * 2) / 2,
                (self.height() - radius * 2) / 2,
                radius * 2,
                radius * 2,
            )
        )


# ============================ КАРТКА ПОВІДОМЛЕННЯ ЧАТУ ============================
class ChatCard(QFrame):
    """A message card for assistant and user messages."""

    def __init__(
        self,
        author: str,
        body: str,
        time: str,
        icon: str,
        is_user: bool = False,
        status: str | None = None,
        status_icon: str | None = None,
        loading: bool = False,
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
            icon_label.setPixmap(load_pixmap(icon, 20))
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

        if loading:
            self.loading_dot = LoadingDot(self)
            header_layout.addWidget(self.loading_dot)

        # Необов'язковий рядок статусу праворуч у заголовку картки.
        if status:
            if status_icon:
                status_icon_label = QLabel()
                status_icon_label.setFixedSize(16, 16)
                status_icon_label.setPixmap(load_pixmap(status_icon, 14))
                header_layout.addWidget(status_icon_label)

            status_label = QLabel(status)
            status_label.setObjectName("messageStatus")
            status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            header_layout.addWidget(status_label)

        text_layout.addLayout(header_layout)

        if body:
            body_label = QLabel(body)
            body_label.setObjectName("messageBody")
            body_label.setWordWrap(True)
            body_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            body_label.setTextFormat(Qt.TextFormat.PlainText)
            text_layout.addWidget(body_label)

        if not loading:
            time_label = QLabel(time)
            time_label.setObjectName("messageTime")
            text_layout.addWidget(time_label)

        layout.addLayout(text_layout, 1)
