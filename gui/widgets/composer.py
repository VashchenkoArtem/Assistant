from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QSize, Qt, pyqtSignal

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
#stopButton {
    border: 1px solid #3c4d7a;
    border-radius: 6px;
    background: #1f2b47;
    color: #ffffff;
    font-size: 13px;
    font-weight: bold;
    min-width: 28px;
    min-height: 28px;
    max-width: 28px;
    max-height: 28px;
    padding: 0px;
}
#stopButton:hover:enabled {
    background: #36202c;
    border-color: #d95364;
    color: #ff9aa6;
}
#stopButton:disabled {
    border: 1px solid #141a2b;
    background: #0a0f1c;
    color: #323c56;
}
#micButton {
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
    stop_requested = pyqtSignal()

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
        composer_layout.setSpacing(10)

        self.stop_button = QPushButton("✕")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setToolTip("Зупинити команду")
        self.stop_button.setFixedSize(28, 28)
        self.stop_button.setEnabled(True)
        self.stop_button.setStyleSheet(
            """
            QPushButton {
                border: 1px solid #2b3550;
                border-radius: 6px;
                background: #141c30;
                color: #d6daf0;
                font-size: 13px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                background: #36202c;
                border-color: #d95364;
                color: #ff9aa6;
            }
            """
        )
        self.stop_button.clicked.connect(self.stop_requested.emit)
        composer_layout.addWidget(self.stop_button, 0, Qt.AlignmentFlag.AlignVCenter)


        self.prompt = AutoResizeTextEdit()
        self.prompt.submitted.connect(self._submit)
        composer_layout.addWidget(self.prompt, 1, Qt.AlignmentFlag.AlignVCenter)

        self.microphone = QPushButton()
        self.microphone.setIcon(make_icon("micro_off.svg", 20))
        self.microphone.setIconSize(QSize(20, 20))
        self.microphone.setObjectName("micButton")
        self.microphone.setFixedSize(32, 32)
        self.microphone.clicked.connect(self.microphone_requested.emit)
        composer_layout.addWidget(self.microphone, 0, Qt.AlignmentFlag.AlignVCenter)


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

    def set_stop_enabled(self, enabled: bool) -> None:
        self.stop_button.setEnabled(True)


    def set_microphone_active(self, active: bool) -> None:
        icon_name = "micro.svg" if active else "micro_off.svg"
        self.microphone.setIcon(make_icon(icon_name, 20))
