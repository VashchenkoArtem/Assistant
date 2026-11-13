from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QWidget,
)

from .icons import make_icon, make_pixmap


STYLE = """
#titleBar {
    background: #080d18;
    border-bottom: 1px solid #11182a;
}
#brand {
    color: #aeb6cc;
    font-size: 13px;
    padding-left: 10px;
}
QToolButton.titleButton {
    border: none;
    background: transparent;
    color: #69718a;
    font-size: 12px;
    min-width: 40px;
    min-height: 48px;
}
QToolButton.titleButton:hover {
    background: #11182a;
}
"""


class TitleBar(QFrame):
    def __init__(self, minimize_callback, maximize_callback, close_callback) -> None:
        super().__init__()
        self.setObjectName("titleBar")
        self.setFixedHeight(49)
        self.setStyleSheet(STYLE)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 5, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        brand_icon = QLabel()
        brand_icon.setPixmap(make_pixmap("logo_assistant.svg", 22))
        brand_icon.setFixedWidth(28)
        brand_icon.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(brand_icon)

        brand = QLabel("Поліна")
        brand.setObjectName("brand")
        brand.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(brand)

        actions = QWidget()
        actions.setFixedSize(132, 49)
        actions.setStyleSheet("background: transparent; border: none;")
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(4)

        for icon_name, callback in (
            ("hide_window.svg", minimize_callback),
            ("full_window.svg", maximize_callback),
            ("close_winow.svg", close_callback),
        ):
            button = QToolButton()
            button.setIcon(make_icon(icon_name, 40))
            button.setIconSize(QSize(40, 49))
            button.setFixedSize(40, 49)
            button.setProperty("class", "titleButton")
            button.clicked.connect(callback)
            actions_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(actions, 0, Qt.AlignmentFlag.AlignVCenter)
