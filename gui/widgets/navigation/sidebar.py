from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QToolButton,
    QVBoxLayout,
)

from ..common.icons import make_icon


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
    home_requested = pyqtSignal()
    profile_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("sidebar")
        self.setMinimumWidth(63)
        self.setMaximumWidth(63)
        self.setFixedWidth(63)
        self.setStyleSheet(STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 12, 2, 8)
        layout.setSpacing(6)

        buttons: list[QToolButton] = []
        self._page_buttons: dict[str, QToolButton] = {}
        for page, icon_name, active, tooltip in (
            ("home", "navigation/home.svg", True, "Головна"),
            ("profile", "chat/user_ico.svg", False, "Персоналізація"),
            ("settings", "navigation/settings.svg", False, "Налаштування"),
        ):
            button = QToolButton()
            button.setIcon(make_icon(icon_name, 22))
            button.setIconSize(QSize(24, 24))
            button.setObjectName("sideButton")
            button.setCheckable(True)
            button.setChecked(active)
            button.setFixedSize(56, 56)
            button.setToolTip(tooltip)
            button.clicked.connect(
                lambda _checked=False, selected=button: self._select(selected, buttons)
            )
            self._page_buttons[page] = button
            if page == "home":
                button.clicked.connect(self.home_requested.emit)
            elif page == "profile":
                button.clicked.connect(self.profile_requested.emit)
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            buttons.append(button)

        layout.addStretch(1)

    @staticmethod
    def _select(selected: QToolButton, buttons: list[QToolButton]) -> None:
        for button in buttons:
            button.setChecked(button is selected)

    def set_active_page(self, page: str) -> None:
        selected = self._page_buttons.get(page)
        if selected is not None:
            self._select(selected, list(self._page_buttons.values()))
