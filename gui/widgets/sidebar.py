from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QFrame,
    QPushButton,
    QToolButton,
    QVBoxLayout,
)

from .icons import make_icon


STYLE = """
#sidebar {
    background: #080d18;
    border-right: 1px solid #11182a;
}
QToolButton.sideButton {
    border: none;
    background: transparent;
    color: #747f9e;
    font-size: 16px;
    min-width: 56px;
    min-height: 56px;
}
QToolButton.sideButton:hover, QToolButton.sideButton:checked {
    background: #151e32;
    color: #d6daf0;
    border-radius: 8px;
}
#languageButton {
    border: none;
    background: transparent;
    color: #747f9e;
    font-size: 10px;
}
#languageButton:hover {
    color: #d6daf0;
    background: #151e32;
    border-radius: 8px;
}
"""


class Sidebar(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("sidebar")
        self.setMinimumWidth(63)
        self.setMaximumWidth(220)
        self.setStyleSheet(STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 12, 2, 8)
        layout.setSpacing(6)

        buttons: list[QToolButton] = []
        for icon_name, active in (
            ("home.svg", True),
            ("user_ico.svg", False),
            ("settings.svg", False),
        ):
            button = QToolButton()
            button.setIcon(make_icon(icon_name, 22))
            button.setIconSize(QSize(24, 24))
            button.setObjectName("sideButton")
            button.setCheckable(True)
            button.setChecked(active)
            button.setFixedSize(56, 56)
            button.clicked.connect(
                lambda _checked=False, selected=button: self._select(selected, buttons)
            )
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            buttons.append(button)

        layout.addStretch(1)
        language_button = QPushButton("УКР")
        language_button.setObjectName("languageButton")
        language_button.setFixedSize(56, 40)
        language_button.clicked.connect(
            lambda: language_button.setText(
                "ENG" if language_button.text() == "УКР" else "УКР"
            )
        )
        layout.addWidget(language_button, 0, Qt.AlignmentFlag.AlignHCenter)

    @staticmethod
    def _select(selected: QToolButton, buttons: list[QToolButton]) -> None:
        for button in buttons:
            button.setChecked(button is selected)
