from typing import Any

from PyQt6.QtCore import QPoint, Qt, QThreadPool
from PyQt6.QtGui import QKeySequence, QMouseEvent, QShortcut
from PyQt6.QtWidgets import (
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .styles import STYLESHEET
from .widgets.chat_panel import ChatPanel
from .widgets.chat_widgets import ChatCard
from utils.voicing_answer import GUI_TEXT_MODE


# ============================ АВТОРОЗШИРЮВАНЕ ПОЛЕ ВВЕДЕННЯ ============================
class AutoResizeTextEdit(QTextEdit):
    """Багаторядкове поле, що росте до максимального розміру, потім прокручуватись."""

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
        self.setStyleSheet("border: none; background: transparent; color: #77819a; padding: 12px 4px;")
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
QToolButton.sideButton { border: none; background: transparent; color: #aeb6cc; font-size: 12px; text-align: left; padding-left: 10px; min-height: 44px; border-radius: 8px; }
QToolButton.sideButton:hover, QToolButton.sideButton:checked { background: #1a1a1a; color: #ffffff; }
QToolButton.sidebarLogo { border: none; background: transparent; border-radius: 8px; text-align: left; padding-left: 12px; }
QToolButton.sidebarLogo:hover { background: #151515; }
#searchBar { background: #080d18; border-bottom: 1px solid #11182a; min-height: 58px; }
#searchField { background: transparent; border: none; color: #77809a; padding-left: 8px; }
#searchButton { border: none; background: transparent; color: #596178; }
#chatScroll, #chatViewport { background: #080e1d; border: none; }
QScrollBar:vertical { border: none; background: #080e1d; width: 6px; }
QScrollBar::handle:vertical { background: #1a2340; border-radius: 3px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: #080e1d; }
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


class CommandSignals(QObject):
    finished = pyqtSignal(str, object)
    error = pyqtSignal(str)


class VoiceSignals(QObject):
    recognized = pyqtSignal(str)
    error = pyqtSignal(str)


class InitializationSignals(QObject):
    finished = pyqtSignal(object, object)


class InitializationWorker(QRunnable):
    """Prepares Django and the assistant command outside the Qt UI thread."""

    def __init__(self, project_root: Path) -> None:
        super().__init__()
        self.project_root = project_root
        self.signals = InitializationSignals()
        self.result_command: object | None = None
        self.result_error: object | None = None
        self._sidebar_expanded = False
        self._sidebar = None
        self._sidebar_buttons = []
        self._sidebar_logo_button = None
        self._body_splitter = None

    def run(self) -> None:
        sys_path = str(self.project_root)
        if sys_path not in sys.path:
            sys.path.insert(0, sys_path)
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Assistant.settings")

        try:
            import django

            django.setup()
            from core.management.commands.run_assistant import Command

            command = Command()
            if hasattr(command, "initialize_for_text"):
                command.initialize_for_text()
                self.result_command = command
                self.signals.finished.emit(command, None)
                return
            self.result_error = "Метод initialize_for_text() не знайдено."
            self.signals.finished.emit(None, "Метод initialize_for_text() не знайдено.")
        except Exception as error:
            self.result_error = str(error)
            self.signals.finished.emit(None, str(error))


class CommandWorker(QRunnable):
    """Runs one assistant command outside the Qt UI thread."""

    def __init__(self, command: Any, text: str, speak_answer: bool = False) -> None:
        super().__init__()
        self.command = command
        self.text = text
        self.speak_answer = speak_answer
        self.signals = CommandSignals()

    def run(self) -> None:
        buffer = io.StringIO()
        try:
            from django.core.management.base import OutputWrapper

            self.command.stdout = OutputWrapper(buffer)
            if not self.speak_answer:
                GUI_TEXT_MODE.set()
            else:
                GUI_TEXT_MODE.clear()
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                self.command.process_recognized_command(self.text)
            output = buffer.getvalue().strip()
            self.signals.finished.emit(self.text, output)
        except Exception as error:
            self.signals.error.emit(str(error))
        finally:
            GUI_TEXT_MODE.clear()


class VoiceWorker(QRunnable):
    """Keeps listening for microphone phrases until it is stopped."""

    def __init__(self) -> None:
        super().__init__()
        self.signals = VoiceSignals()
        self.stop_event = threading.Event()

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        try:
            import speech_recognition

            recognizer = cast(Any, speech_recognition.Recognizer())
            microphone = cast(Any, speech_recognition.Microphone())
            with microphone as source:
                recognizer.dynamic_energy_threshold = True
                recognizer.adjust_for_ambient_noise(source, duration=1)
                recognizer.pause_threshold = 0.6

                while not self.stop_event.is_set():
                    try:
                        audio = recognizer.listen(source, timeout=1, phrase_time_limit=5)
                        if self.stop_event.is_set():
                            break
                        text = recognizer.recognize_google(audio, language="uk-UA")
                        if text.strip() and not self.stop_event.is_set():
                            self.signals.recognized.emit(text.strip())
                    except speech_recognition.WaitTimeoutError:
                        continue
                    except speech_recognition.UnknownValueError:
                        continue
        except Exception as error:
            self.signals.error.emit(str(error))


class MainWindow(QMainWindow):
    """Coordinates the window components and assistant command state."""

    BACKEND_URL = "http://127.0.0.1:8765"

    def __init__(self, command: Any | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Поліна")
        self.resize(908, 907)
        self.setMinimumSize(760, 620)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(STYLESHEET)

        self._drag_position: QPoint | None = None
        self._command_busy = False
        self._command_queue: list[tuple[str, bool]] = []
        self._thread_pool = QThreadPool(self)
        self._voice_busy = False
        self._voice_worker: VoiceWorker | None = None
        self._voice_status_card: ChatCard | None = None
        self._voice_stopped_card: ChatCard | None = None
        self._initialization_worker: BackendHealthWorker | None = None
        self._initialization_status_card: ChatCard | None = None
        self._initializing = True

        self.chat = ChatPanel()
        self.search = SearchBar()
        self.composer = Composer()
        self._build_ui()

        self.search.submitted.connect(self.send_message)
        self.composer.submitted.connect(self.send_message)
        self.search.microphone_requested.connect(self.start_microphone_input)
        self.composer.microphone_requested.connect(self.start_microphone_input)

        shortcut = QShortcut(QKeySequence("Ctrl+M"), self)
        shortcut.activated.connect(self.start_microphone_input)
        self._microphone_shortcut = shortcut

        self._initialization_status_card = self._add_chat_card(
            "System",
            "Підключення до асистента...",
            status="Initializing",
        )
        self._set_commands_enabled(False)
        self._initialization_worker = BackendHealthWorker(self.BACKEND_URL)
        self._initialization_worker.signals.finished.connect(self._backend_initialized)
        self._thread_pool.start(self._initialization_worker)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(
            TitleBar(
                minimize_callback=self.showMinimized,
                maximize_callback=self.toggle_maximize,
                close_callback=self.close,
            )
        )

        body = QSplitter(Qt.Orientation.Horizontal)
        body.setHandleWidth(4)
        body.setChildrenCollapsible(False)
        body.addWidget(Sidebar())

        main_panel = QWidget()
        main_layout = QVBoxLayout(main_panel)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.search)
        main_layout.addWidget(self.chat, 1)
        main_layout.addWidget(self.composer)
        body.addWidget(main_panel)
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setSizes([63, 845])
        root_layout.addWidget(body, 1)

        self.setCentralWidget(root)

    def toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ============================ ЛІВА ПАНЕЛЬ / SIDEBAR ============================
    def _create_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(63)
        sidebar.setMaximumWidth(220)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 12, 0, 8)
        layout.setSpacing(6)

        # Кнопка логотипа для розгортання бічної панелі.
        logo_button = QToolButton()
        logo_button.setObjectName("sidebarLogo")
        logo_button.setText("●")
        logo_button.setAutoRaise(True)
        logo_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        logo_button.setStyleSheet("""
            QToolButton {
                color: white;
                font-size: 27px;
                border: none;
                background: transparent;
                padding: 0px;
                margin: 0px;
            }
            QToolButton:hover {
                background: #151515;
                border-radius: 8px;
            }
        """)
        logo_button.setFixedSize(56, 56)
        layout.addWidget(logo_button, 0, Qt.AlignmentFlag.AlignHCenter)

        # Основні розділи бічної панелі.
        sidebar_buttons = []
        for icon_name, title, active in (
            ("home.svg", "Головна", True),
            ("user_ico.svg", "Профіль", False),
            ("settings.svg", "Налаштування", False),
        ):
            button = QToolButton()
            button.setIcon(self.make_icon(icon_name, 22))
            button.setIconSize(QSize(24, 24))
            button.setObjectName("sideButton")
            button.setCheckable(True)
            button.setChecked(active)
            button.setText("       " + title)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setStyleSheet("""
                QToolButton {
                    border: none;
                    background: transparent;
                    color: white;
                    text-align: left;
                    padding-left: 12px;
                    padding-right: 8px;
                }
                QToolButton:hover {
                    background-color: #303030;
                    border: none;
                }
                QToolButton:checked {
                    background-color: #383838;
                    border: none;
                }
            """)
            button.setFixedSize(56, 56)
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            sidebar_buttons.append(button)

        # Перемикання активного розділу.
        for button in sidebar_buttons:
            button.clicked.connect(
                lambda _checked=False, selected=button:
                    self._select_sidebar_button(selected, sidebar_buttons)
            )

        # Перемикання стану бічної панелі.
        logo_button.clicked.connect(
            lambda: self._toggle_sidebar(sidebar, sidebar_buttons, logo_button)
        )

        # Перемикач мови в нижній частині панелі.
        layout.addStretch(1)
        language_button = QPushButton("УКР")
        language_button.setObjectName("languageButton")
        language_button.setFixedSize(56, 40)

        def toggle_language() -> None:
            language_button.setText(
                "АНГ" if language_button.text() == "УКР" else "УКР"
            )

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

        chat_layout.addStretch()
        scroll.setWidget(viewport)
        self._chat_layout = chat_layout
        self._chat_scroll = scroll
        layout.addWidget(scroll, 1)
        # Нижня панель вводу розміщена окремо під історією повідомлень.
        layout.addWidget(self._create_composer())

        return panel

    def _select_sidebar_button(self, selected: QToolButton, buttons: list[QToolButton]) -> None:
        for button in buttons:
            button.setChecked(button is selected)

    def _add_chat_card(
        self,
        author: str,
        body: str,
        is_user: bool = False,
        status: str | None = None,
    ) -> ChatCard:
        return self.chat.add_card(author, body, is_user=is_user, status=status)

    def _remove_chat_card(self, card: ChatCard | None) -> None:
        if card is None:
            return
        self.chat.chat_layout.removeWidget(card)
        card.setParent(None)
        card.deleteLater()

    def send_message(
        self,
        text: str,
        clear_prompt: Any | None = None,
        clear_search: Any | None = None,
        speak_answer: bool = False,
    ) -> None:
        text = text.strip()
        if not text:
            return
        if self._initializing:
            self._add_chat_card("System", "Зачекайте, асистент ще ініціалізується.")
            return
        if clear_prompt is not None:
            clear_prompt.clear()
        if clear_search is not None:
            clear_search.clear()

        self._remove_voice_stopped_card()
        self._add_chat_card("User", text, is_user=True)
        if self._command_busy:
            self._command_queue.append((text, speak_answer))
            return

        self._start_command(text, speak_answer)

    def _start_command(self, text: str, speak_answer: bool = False) -> None:
        self._command_busy = True
        worker = CommandWorker(self.BACKEND_URL, text, speak_answer=speak_answer)
        worker.signals.finished.connect(self._command_finished)
        worker.signals.error.connect(self._command_failed)
        self._thread_pool.start(worker)

    def _command_finished(self, _text: str, output: object) -> None:
        self._command_busy = False
        lines = str(output).strip().splitlines() if output else []
        lines = [
            line.strip()
            for line in lines
            if line.strip() and not line.strip().startswith("Ви сказали:")
        ]
        if lines:
            self._add_chat_card("Поліна", "\n".join(lines))
        self._start_next_queued_command()

    def _command_failed(self, message: str) -> None:
        self._command_busy = False
        self._add_chat_card("System", f"Помилка виконання команди: {message}")
        self._start_next_queued_command()

    def _start_next_queued_command(self) -> None:
        if self._command_busy or not self._command_queue:
            return
        text, speak_answer = self._command_queue.pop(0)
        self._start_command(text, speak_answer)

    def start_microphone_input(self) -> None:
        if self._initializing:
            return
        if self._voice_busy:
            self.stop_microphone_input()
            return
        self._remove_voice_stopped_card()
        self._voice_busy = True
        self.composer.set_microphone_active(True)
        self._voice_status_card = self._add_chat_card(
            "System",
            "Слухаю вас...",
            status="Recording",
        )
        self._voice_worker = VoiceWorker()
        self._voice_worker.signals.recognized.connect(self._voice_recognized)
        self._voice_worker.signals.error.connect(self._voice_failed)
        self._thread_pool.start(self._voice_worker)

    def stop_microphone_input(self) -> None:
        if self._voice_worker is not None:
            self._voice_worker.stop()
        self._voice_worker = None
        self._voice_busy = False
        self.composer.set_microphone_active(False)
        self._remove_voice_status_card()
        self._remove_voice_stopped_card()
        self._voice_stopped_card = self._add_chat_card(
            "System",
            "Прослуховування микрофона вимкнено.",
        )

    def _voice_recognized(self, text: str) -> None:
        self._remove_voice_status_card()
        self.send_message(text, speak_answer=True)

    def _voice_failed(self, message: str) -> None:
        self._voice_busy = False
        self._voice_worker = None
        self.composer.set_microphone_active(False)
        self._remove_voice_status_card()
        self._add_chat_card("System", f"Не вдалося розпізнати голос: {message}")

    def _remove_voice_status_card(self) -> None:
        self._remove_chat_card(self._voice_status_card)
        self._voice_status_card = None

    def _remove_voice_stopped_card(self) -> None:
        self._remove_chat_card(self._voice_stopped_card)
        self._voice_stopped_card = None

    def _remove_initialization_status_card(self) -> None:
        self._remove_chat_card(self._initialization_status_card)
        self._initialization_status_card = None

    def _set_commands_enabled(self, enabled: bool) -> None:
        self.search.setEnabled(enabled)
        self.composer.set_prompt_enabled(enabled)

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if (
            event is not None
            and self._drag_position is not None
            and event.buttons() == Qt.MouseButton.LeftButton
        ):
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        self._drag_position = None
        if event is not None:
            event.accept()

    def _toggle_sidebar(self, sidebar, sidebar_buttons, logo_button):
        # Перемикання стану бічної панелі.
        expanded = sidebar.width() <= 63
        layout = sidebar.layout()

        if expanded:
            sidebar.setFixedWidth(220)

            logo_button.setFixedSize(56, 56)
            layout.setAlignment(logo_button, Qt.AlignmentFlag.AlignLeft)

            for button in sidebar_buttons:
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                button.setFixedSize(210, 56)
                layout.setAlignment(button, Qt.AlignmentFlag.AlignLeft)
        else:
            sidebar.setFixedWidth(63)

            logo_button.setFixedSize(56, 56)
            layout.setAlignment(logo_button, Qt.AlignmentFlag.AlignHCenter)

            for button in sidebar_buttons:
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setFixedSize(56, 56)
                layout.setAlignment(button, Qt.AlignmentFlag.AlignHCenter)