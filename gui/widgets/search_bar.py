from PyQt6.QtCore import QSize, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from .icons import make_pixmap


STYLE = """
#searchBar {
    background: #080d18;
    border-bottom: 1px solid #11182a;
    min-height: 58px;
}
#searchField {
    background: transparent;
    border: none;
    color: #77809a;
    padding-left: 8px;
}
#searchButton {
    border: none;
    background: transparent;
    color: #596178;
}
"""


class SearchBar(QWidget):
    submitted = pyqtSignal(str)
    microphone_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("searchBar")
        self.setStyleSheet(STYLE)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(23, 8, 12, 8)
        layout.setSpacing(10)

        search_icon = QLabel()
        search_icon.setPixmap(make_pixmap("search.svg", 16))
        layout.addWidget(search_icon)

        self.field = QLineEdit()
        self.field.setObjectName("searchField")
        self.field.setPlaceholderText("Search files, repositories, or start speaking")
        self.field.setFixedHeight(42)
        self.field.returnPressed.connect(self._submit)
        layout.addWidget(self.field, 1)

        self.microphone_button = QPushButton("Ctrl + M")
        self.microphone_button.setObjectName("searchButton")
        self.microphone_button.clicked.connect(self.microphone_requested.emit)
        layout.addWidget(self.microphone_button)

    def _submit(self) -> None:
        text = self.field.text().strip()
        if text:
            self.submitted.emit(text)
            self.field.clear()

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self.field.setEnabled(enabled)
        self.microphone_button.setEnabled(enabled)
