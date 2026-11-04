from pathlib import Path

from PyQt6.QtCore import QPoint, QSize, Qt
from PyQt6.QtGui import QIcon, QImage, QMouseEvent, QPainter, QPixmap, QResizeEvent
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QTextEdit,
)

from .widgets.chat_widgets import ChatCard


# ============================ АВТОРОЗШИРЮВАНЕ ПОЛЕ ВВЕДЕННЯ ============================
class AutoResizeTextEdit(QTextEdit):
    """Багаторядкове поле, що росте до максимального розміру, потім прокручуватись."""

    MIN_HEIGHT = 50
    MAX_HEIGHT = 220

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("promptInput")
        self.setPlaceholderText("Type a message or press the microphone to speak")
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("border: none; background: transparent; color: #77819a; padding: 12px 4px;")
        self.setMinimumHeight(self.MIN_HEIGHT)
        self.setMaximumHeight(self.MAX_HEIGHT)
        self.textChanged.connect(self._resize_to_content)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self._resize_to_content()

    def _resize_to_content(self) -> None:
        viewport = self.viewport()
        document = self.document()
        if viewport is None or document is None:
            return

        available_width = max(40, viewport.width())
        document.setTextWidth(float(available_width))
        document_height = document.size().height()
        new_height = max(self.MIN_HEIGHT, min(self.MAX_HEIGHT, int(document_height + 24)))
        if self.height() != new_height:
            self.setFixedHeight(new_height)

        if document_height + 24 >= self.MAX_HEIGHT:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        else:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)


# ============================ СПІЛЬНІ СТИЛІ GUI ============================
# Тут задаються кольори, фон, шрифти та типові стилі для всіх блоків вікна.
STYLESHEET = """
QMainWindow, QWidget { background: #080e1d; color: #b5bdd4; font-family: 'Segoe UI'; font-size: 11px; }
#titleBar { background: #080d18; border-bottom: 1px solid #11182a; }
#brand { color: #aeb6cc; font-size: 13px; padding-left: 10px; }
#commandBar { background: #090f20; border: 1px solid #10192d; border-radius: 0px; color: #59617a; padding-left: 11px; }
QToolButton.titleButton { border: none; background: transparent; color: #69718a; font-size: 12px; min-width: 40px; min-height: 48px; }
QToolButton.titleButton:hover { background: #11182a; }
#sidebar { background: #080d18; border-right: 1px solid #11182a; }
QToolButton.sideButton { border: none; background: transparent; color: #747f9e; font-size: 16px; min-width: 56px; min-height: 56px; }
QToolButton.sideButton:hover, QToolButton.sideButton:checked { background: #151e32; color: #d6daf0; border-radius: 8px; }
#searchBar { background: #080d18; border-bottom: 1px solid #11182a; min-height: 58px; }
#searchField { background: transparent; border: none; color: #77809a; padding-left: 8px; }
#searchButton { border: none; background: transparent; color: #596178; }
#chatScroll, #chatViewport { background: #080e1d; border: none; }
QScrollBar:vertical { border: none; background: transparent; width: 6px; }
QScrollBar::handle:vertical { background: #1a2340; border-radius: 3px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
ChatCard { border-radius: 7px; }
#assistantCard { background: transparent; }
#userCard { background: #30384b; }
#userCard QLabel { background: transparent; border: none; }
#assistantCard QLabel { background: transparent; border: none; }
#cardIcon { background: transparent; color: #9ba5bd; border: none; font-size: 15px; }
#messageAuthor { color: #747c96; font-size: 12px; }
#messageBody { color: #788199; font-size: 11px; }
#messageTime { color: #46516b; font-size: 9px; }
#messageStatus { color: #5167c6; font-size: 10px; }
#composerArea { background: #080e1d; border-top: 1px solid #11182a; }
#composer { background: #080d18; border: 1px solid #11182a; border-radius: 6px; min-height: 50px; }
#promptInput { border: none; background: transparent; color: #77819a; }
#promptInput QScrollBar:vertical { width: 5px; }
#micButton, #keyboardButton { border: none; background: transparent; color: #9aa5c1; min-width: 32px; min-height: 32px; }
#languageButton { border: none; background: transparent; color: #747f9e; font-size: 10px; }
#languageButton:hover { color: #d6daf0; background: #151e32; border-radius: 8px; }
"""


class MainWindow(QMainWindow):
    """Main application window matching the assistant desktop prototype."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Поліна")
        self.resize(908, 907)
        self.setMinimumSize(760, 620)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(STYLESHEET)

        self._drag_position: QPoint | None = None
        self._build_ui()

    # ============================ РОБОТА З ІКОНКАМИ ============================
    def icon_path(self, name: str) -> Path:
        assets = Path(__file__).parent / "assets"
        png_path = assets / "png" / f"{Path(name).stem}.png"
        if png_path.exists():
            return png_path
        return assets / name

    def make_icon(self, name: str, size: int = 20) -> QIcon:
        pixmap = self.make_pixmap(name, size)
        return QIcon(pixmap)

    def make_pixmap(self, name: str, size: int) -> QPixmap:
        path = self.icon_path(name)
        if path.suffix.lower() == ".svg":
            renderer = QSvgRenderer(str(path))
            if not renderer.isValid():
                return QPixmap()
            canvas_size = max(size * 4, 64)
            image = QImage(canvas_size, canvas_size, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            renderer.render(painter)
            painter.end()
            pixmap = QPixmap.fromImage(image)
        else:
            pixmap = QPixmap(str(path))

        if pixmap.isNull():
            return QPixmap()

        image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        rect = image.size().boundedTo(QSize(image.width(), image.height()))
        left, top, right, bottom = rect.width(), rect.height(), -1, -1
        for y in range(rect.height()):
            for x in range(rect.width()):
                if image.pixelColor(x, y).alpha() >= 24:
                    left = min(left, x)
                    top = min(top, y)
                    right = max(right, x)
                    bottom = max(bottom, y)

        if right >= left and bottom >= top:
            pixmap = QPixmap.fromImage(image.copy(left, top, right - left + 1, bottom - top + 1))

        return pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

    # ============================ ОСНОВНА КОМПОНОВКА ВІКНА ============================
    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._create_title_bar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._create_sidebar())
        body.addWidget(self._create_main_panel(), 1)
        root_layout.addLayout(body, 1)

        self.setCentralWidget(root)

    # ============================ ВЕРХНЯ ПАНЕЛЬ / TITLE BAR ============================
    def _create_title_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(49)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 5, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Верхня ліва частина без окремого фонового прямокутника.
        brand_icon = QLabel()
        brand_icon.setPixmap(self.make_pixmap("logo_assistant.svg", 22))
        brand_icon.setFixedWidth(28)
        brand_icon.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(brand_icon)

        brand = QLabel("Поліна")
        brand.setObjectName("brand")
        brand.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(brand)

        # Права група керування вікном: повноформатні кнопки на всю висоту заголовка.
        actions = QWidget()
        actions.setFixedSize(132, 49)
        actions.setStyleSheet("background: transparent; border: none;")
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(4)

        title_actions = (
            ("hide_window.svg", self.showMinimized),
            ("full_window.svg", self.showMaximized),
            ("close_winow.svg", self.close),
        )
        for icon_name, callback in title_actions:
            button = QToolButton()
            button.setIcon(self.make_icon(icon_name, 40))
            button.setIconSize(QSize(40, 49))
            button.setFixedSize(40, 49)
            button.setProperty("class", "titleButton")
            # Іконка/фото є повним виглядом кнопки; прозорий фон не накладається.
            button.setStyleSheet(
                "QToolButton { border: none; background: transparent; }"
                "QToolButton:hover { background: transparent; }"
            )
            button.clicked.connect(callback)
            actions_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(actions, 0, Qt.AlignmentFlag.AlignVCenter)
        return bar

    # ============================ ЛІВА ПАНЕЛЬ / SIDEBAR ============================
    def _create_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(63)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(2, 12, 2, 8)
        layout.setSpacing(6)

        # Верхній блок лівої панелі: головна сторінка, налаштування, профіль.
        for icon_name, active in (("home.svg", True), ("user_ico.svg", False), ("settings.svg", False)):
            button = QToolButton()
            button.setIcon(self.make_icon(icon_name, 22))
            button.setIconSize(QSize(24, 24))
            button.setObjectName("sideButton")
            button.setCheckable(True)
            button.setChecked(active)
            button.setFixedSize(56, 56)
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)

        # Знизу залишено лише компактний перемикач української та англійської мов.
        layout.addStretch(1)
        language_button = QPushButton("УКР")
        language_button.setObjectName("languageButton")
        language_button.setFixedSize(56, 40)

        def toggle_language() -> None:
            language_button.setText("ENG" if language_button.text() == "УКР" else "УКР")

        language_button.clicked.connect(toggle_language)
        layout.addWidget(language_button, 0, Qt.AlignmentFlag.AlignHCenter)

        return sidebar

    # ============================ ЦЕНТРАЛЬНА ПАНЕЛЬ ============================
    def _create_main_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._create_search_bar())

        # Область історії повідомлень посередині центральної панелі.
        scroll = QScrollArea()
        scroll.setObjectName("chatScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        viewport = QWidget()
        viewport.setObjectName("chatViewport")
        chat_layout = QVBoxLayout(viewport)
        chat_layout.setContentsMargins(16, 10, 16, 16)
        chat_layout.setSpacing(8)

        # Повідомлення асистента.
        bot_card = ChatCard("Поліна", "Here is the overview you requested! Highlights: the active audio channel and latest logs.", "2:58 PM", str(self.icon_path("bot_ico.svg")))
        chat_layout.addWidget(bot_card)

        # Повідомлення користувача — окрема картка іншого кольору.
        user_card = ChatCard(
            "User",
            "Start continuous monitoring and summarize privacy events since boot",
            "2:58 PM",
            str(self.icon_path("user_ico.svg")),
            is_user=True,
        )
        chat_layout.addWidget(user_card)

        # Повідомлення асистента зі статусом Recording.
        chat_layout.addWidget(ChatCard(
            "Поліна",
            "Compiling results are applying privacy filters. Preparing secure summary…",
            "2:58 PM",
            str(self.icon_path("bot_ico.svg")),
            status="Recording",
            status_icon=str(self.icon_path("status.svg")),
        ))

        # Системне повідомлення в чаті.
        chat_layout.addWidget(ChatCard(
            "System",
            "Microphone hardware mute triggered at 2:30 PM — hardware cutoff enforced",
            "2:58 PM",
            str(self.icon_path("info.svg")),
        ))

        chat_layout.addStretch()
        scroll.setWidget(viewport)
        layout.addWidget(scroll, 1)
        # Нижня панель вводу розміщена окремо під історією повідомлень.
        layout.addWidget(self._create_composer())

        return panel

    # ============================ РЯДОК ПОШУКУ НАД ЧАТОМ ============================
    def _create_search_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("searchBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(23, 8, 12, 8)
        layout.setSpacing(10)

        # Іконка пошуку ліворуч у рядку пошуку.
        search_icon = QLabel()
        search_icon.setPixmap(self.make_pixmap("search.svg", 16))
        layout.addWidget(search_icon)

        search = QLineEdit()
        search.setObjectName("searchField")
        search.setPlaceholderText("Search files, repositories, or start speaking")
        search.setFixedHeight(42)
        layout.addWidget(search, 1)

        filter_button = QPushButton("Ctrl + M")
        filter_button.setObjectName("searchButton")
        layout.addWidget(filter_button)
        return bar

    # ============================ НИЖНЯ ПАНЕЛЬ ВВЕДЕННЯ ============================
    def _create_composer(self) -> QWidget:
        # Нижня панель вводу має динамічно зростати разом із текстом.
        area = QWidget()
        area.setObjectName("composerArea")

        layout = QVBoxLayout(area)
        layout.setContentsMargins(16, 12, 16, 10)
        layout.setSpacing(9)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        area.setMaximumHeight(300)

        composer = QFrame()
        composer.setObjectName("composer")
        composer_layout = QHBoxLayout(composer)
        composer_layout.setContentsMargins(12, 4, 12, 4)
        composer_layout.setSpacing(8)

        # Ліва кнопка системної дієї прив’язана до нижнього краю поля.
        keyboard = QPushButton()
        keyboard.setIcon(self.make_icon("system_enter.svg", 20))
        keyboard.setIconSize(QSize(20, 20))
        keyboard.setObjectName("keyboardButton")
        keyboard.setFixedSize(32, 32)
        composer_layout.addWidget(keyboard, 0, Qt.AlignmentFlag.AlignBottom)

        # Багаторядкове поле автоматично розширює composer, але прокручується після max-height.
        prompt = AutoResizeTextEdit()
        composer_layout.addWidget(prompt, 1, Qt.AlignmentFlag.AlignVCenter)

        mic = QPushButton()
        mic.setIcon(self.make_icon("micro.svg", 20))
        mic.setIconSize(QSize(20, 20))
        mic.setObjectName("micButton")
        mic.setFixedSize(32, 32)
        composer_layout.addWidget(mic, 0, Qt.AlignmentFlag.AlignBottom)

        layout.addWidget(composer, 0, Qt.AlignmentFlag.AlignVCenter)

        def resize_composer_area() -> None:
            input_height = prompt.height()
            composer_height = max(50, input_height + 8)
            composer.setFixedHeight(composer_height)
            area.updateGeometry()

        prompt.textChanged.connect(resize_composer_area)
        resize_composer_area()
        return area

    # ============================ ПЕРЕТЯГУВАННЯ ВІКНА ============================
    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and self._drag_position is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        self._drag_position = None
        if event is not None:
            event.accept()
