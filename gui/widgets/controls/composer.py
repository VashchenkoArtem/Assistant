from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..common.icons import make_icon
from .input import AutoResizeTextEdit


STYLE = """
#composerArea {
    background: #080e1d;
    border-top: 1px solid #11182a;
}
#composer {
    background: #080d18;
    border: 1px solid #11182a;
    border-radius: 6px;
    min-height: 50px;
}
#micButton, #sendButton {
    border: none;
    background: transparent;
    color: #9aa5c1;
    min-width: 32px;
    min-height: 32px;
}
#sendButton:hover:enabled {
    background: #151e32;
    border-radius: 6px;
}
"""


class Composer(QWidget):
    submitted = pyqtSignal(str)
    microphone_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("composerArea")
        self.setStyleSheet(STYLE)
        self.setMaximumHeight(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 10)
        layout.setSpacing(9)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        composer = QFrame()
        composer.setObjectName("composer")
        composer_layout = QHBoxLayout(composer)
        composer_layout.setContentsMargins(12, 4, 12, 4)
        composer_layout.setSpacing(8)

        self.prompt = AutoResizeTextEdit()
        self.prompt.submitted.connect(self._submit)
        composer_layout.addWidget(self.prompt, 1, Qt.AlignmentFlag.AlignVCenter)

        self.microphone = QPushButton()
        self.microphone.setIcon(make_icon("controls/micro_off.svg", 20))
        self.microphone.setIconSize(QSize(20, 20))
        self.microphone.setObjectName("micButton")
        self.microphone.setFixedSize(32, 32)
        self.microphone.setToolTip("Увімкнути або вимкнути мікрофон")
        self.microphone.clicked.connect(self.microphone_requested.emit)
        composer_layout.addWidget(self.microphone, 0, Qt.AlignmentFlag.AlignBottom)

        self.send_button = QPushButton()
        self.send_button.setObjectName("sendButton")
        self.send_button.setIconSize(QSize(20, 20))
        self.send_button.setFixedSize(32, 32)
        self.send_button.setToolTip("Надіслати повідомлення")
        self.send_button.clicked.connect(self._submit)
        composer_layout.addWidget(self.send_button, 0, Qt.AlignmentFlag.AlignBottom)

        layout.addWidget(composer, 0, Qt.AlignmentFlag.AlignVCenter)

        def resize_composer() -> None:
            composer.setFixedHeight(max(50, self.prompt.height() + 8))
            self.updateGeometry()

        self.prompt.textChanged.connect(resize_composer)
        self.prompt.textChanged.connect(self._update_send_button)
        self._update_send_button()
        resize_composer()

    def _update_send_button(self) -> None:
        enabled = self.prompt.isEnabled() and bool(self.prompt.toPlainText().strip())
        icon_name = (
            "controls/airplane_active.svg"
            if enabled
            else "controls/airplane_inactive.svg"
        )
        self.send_button.setIcon(make_icon(icon_name, 20))
        self.send_button.setEnabled(enabled)
        cursor = (
            Qt.CursorShape.PointingHandCursor
            if enabled
            else Qt.CursorShape.ArrowCursor
        )
        self.send_button.setCursor(cursor)

    def _submit(self) -> None:
        text = self.prompt.toPlainText().strip()
        if text:
            self.submitted.emit(text)
            self.prompt.clear()

    def set_prompt_enabled(self, enabled: bool) -> None:
        self.prompt.setEnabled(enabled)
        self.microphone.setEnabled(enabled)
        self._update_send_button()

    def set_microphone_active(self, active: bool) -> None:
        icon_name = "controls/micro.svg" if active else "controls/micro_off.svg"
        self.microphone.setIcon(make_icon(icon_name, 20))
