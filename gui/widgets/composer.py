from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .icons import make_icon
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
#micButton, #keyboardButton {
    border: none;
    background: transparent;
    color: #9aa5c1;
    min-width: 32px;
    min-height: 32px;
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

        self.keyboard = QPushButton()
        self.keyboard.setIcon(make_icon("system_enter.svg", 20))
        self.keyboard.setIconSize(QSize(20, 20))
        self.keyboard.setObjectName("keyboardButton")
        self.keyboard.setFixedSize(32, 32)
        self.keyboard.clicked.connect(self._submit)
        composer_layout.addWidget(self.keyboard, 0, Qt.AlignmentFlag.AlignBottom)

        self.prompt = AutoResizeTextEdit()
        self.prompt.submitted.connect(self._submit)
        composer_layout.addWidget(self.prompt, 1, Qt.AlignmentFlag.AlignVCenter)

        self.microphone = QPushButton()
        self.microphone.setIcon(make_icon("micro_off.svg", 20))
        self.microphone.setIconSize(QSize(20, 20))
        self.microphone.setObjectName("micButton")
        self.microphone.setFixedSize(32, 32)
        self.microphone.clicked.connect(self.microphone_requested.emit)
        composer_layout.addWidget(self.microphone, 0, Qt.AlignmentFlag.AlignBottom)

        layout.addWidget(composer, 0, Qt.AlignmentFlag.AlignVCenter)

        def resize_composer() -> None:
            composer.setFixedHeight(max(50, self.prompt.height() + 8))
            self.updateGeometry()

        self.prompt.textChanged.connect(resize_composer)
        resize_composer()

    def _submit(self) -> None:
        text = self.prompt.toPlainText().strip()
        if text:
            self.submitted.emit(text)
            self.prompt.clear()

    def set_prompt_enabled(self, enabled: bool) -> None:
        self.prompt.setEnabled(enabled)
        self.microphone.setEnabled(enabled)
        self.keyboard.setEnabled(enabled)

    def set_microphone_active(self, active: bool) -> None:
        icon_name = "micro.svg" if active else "micro_off.svg"
        self.microphone.setIcon(make_icon(icon_name, 20))
