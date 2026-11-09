from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QResizeEvent
from PyQt6.QtWidgets import QTextEdit, QWidget


class AutoResizeTextEdit(QTextEdit):
    """Multiline input that grows until its maximum height."""

    MIN_HEIGHT = 50
    MAX_HEIGHT = 220
    submitted = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("promptInput")
        self.setPlaceholderText("Type a message or press the microphone to speak")
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(
            "border: none; background: transparent; color: #77819a; padding: 12px 4px;"
        )
        self.setMinimumHeight(self.MIN_HEIGHT)
        self.setMaximumHeight(self.MAX_HEIGHT)
        self.textChanged.connect(self._resize_to_content)

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if (
            event is not None
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        ):
            self.submitted.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self._resize_to_content()

    def _resize_to_content(self) -> None:
        viewport = self.viewport()
        document = self.document()
        if viewport is None or document is None:
            return

        document.setTextWidth(float(max(40, viewport.width())))
        document_height = document.size().height()
        new_height = max(self.MIN_HEIGHT, min(self.MAX_HEIGHT, int(document_height + 24)))
        if self.height() != new_height:
            self.setFixedHeight(new_height)

        if document_height + 24 >= self.MAX_HEIGHT:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        else:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
