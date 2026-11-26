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
QToolButton#sideButton {
    border: none;
    background: transparent;
    color: #747f9e;
    font-size: 14px;
}
QToolButton#sideButton:hover, QToolButton#sideButton:checked {
    background: #151e32;
    color: #d6daf0;
    border-radius: 8px;
}
#sidebarLogo {
    border: none;
    background: transparent;
}
#sidebarLogo:hover {
    background: #151e32;
    border-radius: 8px;
}
"""


class Sidebar(QFrame):
    home_requested = pyqtSignal()
    profile_requested = pyqtSignal()
    settings_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(63)
        self.setStyleSheet(STYLE)

        layout = QVBoxLayout(self)
        self._layout = layout
        layout.setContentsMargins(2, 12, 2, 8)
        layout.setSpacing(6)

        self._expanded = False
        self._logo_button = QToolButton()
        self._logo_button.setObjectName("sidebarLogo")
        self._logo_button.setIcon(make_icon("branding/logo_assistant.svg", 22))
        self._logo_button.setIconSize(QSize(24, 24))
        self._logo_button.setFixedSize(44, 44)
        self._logo_button.setToolTip("Розгорнути панель")
        self._logo_button.clicked.connect(self.toggle_expanded)
        layout.addWidget(self._logo_button, 0, Qt.AlignmentFlag.AlignHCenter)

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
            button.setText(tooltip)
            button.setCheckable(True)
            button.setChecked(active)
            button.setFixedSize(44, 44)
            button.setToolTip(tooltip)
            button.clicked.connect(
                lambda _checked=False, selected=button: self._select(selected, buttons)
            )
            self._page_buttons[page] = button
            if page == "home":
                button.clicked.connect(self.home_requested.emit)
            elif page == "profile":
                button.clicked.connect(self.profile_requested.emit)
            elif page == "settings":
                button.clicked.connect(self.settings_requested.emit)
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            buttons.append(button)

        layout.addStretch(1)

    def toggle_expanded(self) -> None:
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self.setFixedWidth(220 if expanded else 63)
        alignment = (
            Qt.AlignmentFlag.AlignLeft
            if expanded
            else Qt.AlignmentFlag.AlignHCenter
        )
        self._layout.setContentsMargins(
            8 if expanded else 2, 12, 8 if expanded else 2, 8
        )
        self._layout.setAlignment(self._logo_button, alignment)
        self._logo_button.setToolTip(
            "Згорнути панель" if expanded else "Розгорнути панель"
        )
        for button in self._page_buttons.values():
            button.setFixedSize(200 if expanded else 44, 44)
            button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon
                if expanded
                else Qt.ToolButtonStyle.ToolButtonIconOnly
            )
            self._layout.setAlignment(button, alignment)

    @staticmethod
    def _select(selected: QToolButton, buttons: list[QToolButton]) -> None:
        for button in buttons:
            button.setChecked(button is selected)

    def set_active_page(self, page: str) -> None:
        selected = self._page_buttons.get(page)
        if selected is not None:
            self._select(selected, list(self._page_buttons.values()))
