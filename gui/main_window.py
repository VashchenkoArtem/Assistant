from typing import Any

from PyQt6.QtCore import QPoint, Qt, QThreadPool
from PyQt6.QtGui import QKeySequence, QMouseEvent, QShortcut
from PyQt6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .styles import STYLESHEET
from .widgets.chat_panel import ChatPanel
from .widgets.chat_widgets import ChatCard
from .widgets.composer import Composer
from .widgets.search_bar import SearchBar
from .widgets.sidebar import Sidebar
from .widgets.title_bar import TitleBar
from .workers import BackendHealthWorker, CommandWorker, VoiceWorker


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

    def _backend_initialized(self, ready: object, error: object) -> None:
        self._initializing = False
        if bool(ready):
            self._remove_initialization_status_card()
            self._set_commands_enabled(True)
            self._add_chat_card(
                "Поліна",
                "Привіт! Напишіть команду або натисніть кнопку микрофона.",
            )
            return

        self._remove_initialization_status_card()
        self._set_commands_enabled(False)
        self._add_chat_card(
            "System",
            str(error)
            if error
            else "Бекенд асистента недоступний. Запустіть Django у окремому терміналі.",
        )

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
