from PyQt6.QtCore import QPointF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QResizeEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .icons import make_icon


STYLE = """
#sidebar {
    background: #080d18;
    border-right: 1px solid #11182a;
}
QToolButton#sideButton, QToolButton.sideButton {
    border: none;
    background: transparent;
    color: #9ba5bd;
    font-size: 13px;
    font-weight: 500;
    padding: 0px;
    margin: 0px;
    min-height: 56px;
}
QToolButton#sideButton:hover, QToolButton#sideButton:checked,
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
    padding: 0px;
}
#languageButton:hover {
    color: #d6daf0;
    background: #151e32;
    border-radius: 8px;
}
"""


def _make_left_arrow_icon(size: int = 20, color: str = "#9ba5bd") -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    pen = QPen(QColor(color))
    pen.setWidthF(1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)

    mid_y = size / 2.0
    left_x = size * 0.25
    right_x = size * 0.75
    head = size * 0.22

    painter.drawLine(QPointF(right_x, mid_y), QPointF(left_x, mid_y))
    painter.drawLine(QPointF(left_x + head, mid_y - head), QPointF(left_x, mid_y))
    painter.drawLine(QPointF(left_x + head, mid_y + head), QPointF(left_x, mid_y))

    painter.end()
    return QIcon(pixmap)


class Sidebar(QFrame):
    COLLAPSED_WIDTH = 72
    EXPANDED_WIDTH = 220
    collapsed_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("sidebar")
        self.setMinimumWidth(self.COLLAPSED_WIDTH)
        self.setMaximumWidth(self.EXPANDED_WIDTH)
        self.setStyleSheet(STYLE)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 12, 8, 8)
        self._layout.setSpacing(6)

        # кнопка закрытия 
        self._top_bar = QWidget()
        self._top_bar.setStyleSheet("background: transparent; border: none;")
        self._top_bar_layout = QHBoxLayout(self._top_bar)
        self._top_bar_layout.setContentsMargins(0, 0, 0, 4)
        self._top_bar_layout.setSpacing(0)
        self._top_bar_layout.addStretch(1)

        self._collapse_button = QToolButton()
        self._collapse_button.setObjectName("collapseButton")
        self._collapse_button.setToolTip("Згорнути меню")
        self._collapse_button.setIcon(_make_left_arrow_icon(20, "#9ba5bd"))
        self._collapse_button.setIconSize(QSize(20, 20))
        self._collapse_button.setFixedSize(36, 36)
        self._collapse_button.setStyleSheet(
            """
            QToolButton {
                border: none;
                border-radius: 8px;
                background: #151e32;
                padding: 0px;
            }
            QToolButton:hover {
                background: #1f2b47;
            }
            """
        )
        self._collapse_button.clicked.connect(self.collapse)
        self._top_bar_layout.addWidget(self._collapse_button, 0, Qt.AlignmentFlag.AlignRight)

        self._top_bar.setVisible(False)
        self._layout.addWidget(self._top_bar)

        self._buttons: list[QToolButton] = []
        self._top_buttons: list[tuple[QToolButton, str]] = []

        for icon_name, label, active in (
            ("home.svg", "Головна", True),
            ("user_ico.svg", "Профіль", False),
        ):
            button = self._create_side_button(icon_name, label, active)
            self._layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            self._top_buttons.append((button, label))

        self._layout.addStretch(1)

        # Нижняя панель: язык слева и настройки справа
        self._bottom_bar = QWidget()
        self._bottom_bar.setStyleSheet("background: transparent; border: none;")
        self._bottom_layout = QHBoxLayout(self._bottom_bar)
        self._bottom_layout.setContentsMargins(0, 0, 0, 0)
        self._bottom_layout.setSpacing(0)

        self._language_button = QPushButton("УКР")
        self._language_button.setObjectName("languageButton")
        self._language_button.setFixedSize(56, 56)
        self._language_button.clicked.connect(
            lambda: self._language_button.setText(
                "ENG" if self._language_button.text() == "УКР" else "УКР"
            )
        )

        self._settings_button = self._create_side_button("settings.svg", "", False)

        self._bottom_layout.addWidget(self._language_button)
        self._bottom_stretch_added = True
        self._bottom_layout.addStretch(1)
        self._bottom_layout.addWidget(self._settings_button)

        self._layout.addWidget(self._bottom_bar)
        self._update_responsive_layout()

    def _create_side_button(self, icon_name: str, label: str, active: bool) -> QToolButton:
        button = QToolButton()
        button.setIcon(make_icon(icon_name, 22))
        button.setIconSize(QSize(24, 24))
        button.setText(f"   {label}" if label else "")
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setProperty("class", "sideButton")
        button.setObjectName("sideButton")
        button.setCheckable(True)
        button.setChecked(active)
        button.setFixedSize(56, 56)
        button.clicked.connect(
            lambda _checked=False, selected=button: self._select(selected, self._buttons)
        )
        self._buttons.append(button)
        return button

    def collapse(self) -> None:
        """Згортає бічну панель до мінімальної ширини."""
        self.setMinimumWidth(self.COLLAPSED_WIDTH)
        self.setMaximumWidth(self.EXPANDED_WIDTH)
        parent = self.parentWidget()
        if isinstance(parent, QSplitter):
            sizes = parent.sizes()
            if len(sizes) >= 2:
                total = sum(sizes)
                parent.setSizes([self.COLLAPSED_WIDTH, max(0, total - self.COLLAPSED_WIDTH)])
        else:
            self.resize(self.COLLAPSED_WIDTH, self.height())
        self._update_responsive_layout()
        self.collapsed_requested.emit()

    def expand(self) -> None:
        """Розгортає бічну панель (для виклику кнопкою відкриття)."""
        parent = self.parentWidget()
        if isinstance(parent, QSplitter):
            sizes = parent.sizes()
            if len(sizes) >= 2:
                total = sum(sizes)
                parent.setSizes([self.EXPANDED_WIDTH, max(0, total - self.EXPANDED_WIDTH)])
        else:
            self.resize(self.EXPANDED_WIDTH, self.height())
        self._update_responsive_layout()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_responsive_layout()

    def _update_responsive_layout(self) -> None:
        is_expanded = self.width() > 95
        self._top_bar.setVisible(is_expanded)
        self._language_button.setVisible(is_expanded)

        for button, label in self._top_buttons:
            if is_expanded:
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                button.setText(f"   {label}")
                button.setMinimumWidth(56)
                button.setMaximumWidth(16777215)
                button.setFixedHeight(56)
                button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                button.setStyleSheet("padding-left: 16px; text-align: left;")
                self._layout.setAlignment(button, Qt.AlignmentFlag(0))
            else:
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setText("")
                button.setFixedSize(56, 56)
                button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                button.setStyleSheet("padding: 0px;")
                self._layout.setAlignment(button, Qt.AlignmentFlag.AlignHCenter)

        if is_expanded and not self._bottom_stretch_added:
            self._bottom_layout.insertStretch(1, 1)
            self._bottom_stretch_added = True
        elif not is_expanded and self._bottom_stretch_added:
            item = self._bottom_layout.takeAt(1)
            if item is not None:
                del item
            self._bottom_stretch_added = False

        self._bottom_layout.setAlignment(
            self._settings_button,
            Qt.AlignmentFlag.AlignRight if is_expanded else Qt.AlignmentFlag.AlignHCenter,
        )

    @staticmethod
    def _select(selected: QToolButton, buttons: list[QToolButton]) -> None:
        for button in buttons:
            button.setChecked(button is selected)
