import threading
import time
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QThreadPool, QTimer
from PyQt6.QtGui import QIcon, QKeySequence, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from utils.llm_config import LLMConfigError
from utils.voicing_answer import interrupt_voice

from .icon_loader import icon_path as resolve_icon_path, load_pixmap
from .styles import STYLESHEET
from .widgets.chat.chat_panel import ChatPanel
from .widgets.chat.chat_widgets import ChatCard
from .widgets.controls.composer import Composer
from .widgets.settings.audio_settings_dialog import AudioSettingsDialog
from .widgets.settings.llm_settings_dialog import LLMSettingsPanel
from .widgets.controls.search_bar import SearchBar
from .widgets.navigation.sidebar import Sidebar
from .widgets.navigation.title_bar import TitleBar
from .workers import CommandWorker, InitializationWorker, VoiceWorker


class MainWindow(QMainWindow):
    """Coordinates the window components and assistant command state."""

    def __init__(self, command: Any | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Поліна")
        self.resize(908, 907)
        self.setMinimumSize(760, 620)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(STYLESHEET)

        self._command_busy = False
        self._command_cancel_event: threading.Event | None = None
        self._model_loading_card: ChatCard | None = None
        self._command_queue: list[tuple[str, bool]] = []
        self._thread_pool = QThreadPool(self)
        self._command_timer = QTimer(self)
        self._command_timer.setInterval(50)
        self._command_timer.timeout.connect(self._update_command_timer)
        self._command_started_at: float | None = None
        self._command_status_card: ChatCard | None = None
        self._voice_busy = False
        self._voice_worker: VoiceWorker | None = None
        self._voice_status_card: ChatCard | None = None
        self._voice_stopped_card: ChatCard | None = None
        self._initialization_worker: InitializationWorker | None = None
        self._initialization_status_card: ChatCard | None = None
        self._command = command
        self._initializing = command is None

        self.chat = ChatPanel()
        self._chat_layout = self.chat.chat_layout
        self.search = SearchBar()
        self.composer = Composer()
        self._content_stack = QStackedWidget()
        self._chat_page = QWidget()
        self._settings_panel: LLMSettingsPanel | None = None
        self._audio_settings_panel: AudioSettingsDialog | None = None
        self._build_ui()

        self.search.submitted.connect(self.send_message)
        self.composer.submitted.connect(self.send_message)
        self.search.microphone_requested.connect(self.start_microphone_input)
        self.composer.microphone_requested.connect(self.start_microphone_input)

        shortcut = self.addAction("Мікрофон")
        shortcut.setShortcut(QKeySequence("Ctrl+M"))
        shortcut.triggered.connect(self.start_microphone_input)
        self._microphone_shortcut = shortcut

        if command is None:
            self._initialization_status_card = self.chat.add_card(
                "Система",
                "Підключення до асистента...",
                status="Ініціалізація",
            )
            self._set_commands_enabled(False)
            self._start_initialization()
        else:
            self._set_commands_enabled(True)

    def icon_path(self, name: str) -> Path:
        return resolve_icon_path(name)

    def make_icon(self, name: str, size: int = 20) -> QIcon:
        return QIcon(load_pixmap(self.icon_path(name), size))

    def make_pixmap(self, name: str, size: int) -> QPixmap:
        return load_pixmap(self.icon_path(name), size)

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
        body.setHandleWidth(0)
        body.setChildrenCollapsible(False)
        self.sidebar = Sidebar()
        self.sidebar.profile_requested.connect(self.open_personalization)
        self.sidebar.home_requested.connect(self.show_chat)
        self.sidebar.settings_requested.connect(self.open_audio_settings)
        body.addWidget(self.sidebar)

        main_layout = QVBoxLayout(self._chat_page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.search)
        main_layout.addWidget(self.chat, 1)
        main_layout.addWidget(self.composer)
        self._content_stack.addWidget(self._chat_page)
        body.addWidget(self._content_stack)
        body.setSizes([63, 845])
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        root_layout.addWidget(body, 1)
        self.setCentralWidget(root)

    def toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def open_personalization(self) -> None:
        try:
            if self._settings_panel is None:
                self._settings_panel = LLMSettingsPanel(self._content_stack)
                self._settings_panel.back_requested.connect(self.show_chat)
                self._settings_panel.saved.connect(self._llm_settings_saved)
                self._content_stack.addWidget(self._settings_panel)
        except LLMConfigError as error:
            QMessageBox.critical(self, "Помилка налаштувань LLM", str(error))
            self.sidebar.set_active_page("home")
            return
        self._content_stack.setCurrentWidget(self._settings_panel)
        self.sidebar.set_active_page("profile")

    def show_chat(self) -> None:
        self._content_stack.setCurrentWidget(self._chat_page)
        self.sidebar.set_active_page("home")

    def open_audio_settings(self) -> None:
        if self._audio_settings_panel is None:
            self._audio_settings_panel = AudioSettingsDialog(self._content_stack)
            self._audio_settings_panel.back_requested.connect(self.show_chat)
            self._content_stack.addWidget(self._audio_settings_panel)
        self._content_stack.setCurrentWidget(self._audio_settings_panel)
        self.sidebar.set_active_page("settings")

    def _llm_settings_saved(self) -> None:
        self._command = self._command

    def _start_initialization(self) -> None:
        self._initializing = True
        self._set_commands_enabled(False)
        project_root = Path(__file__).resolve().parents[1]
        self._initialization_worker = InitializationWorker(project_root)
        self._initialization_worker.signals.finished.connect(self._assistant_initialized)
        self._thread_pool.start(self._initialization_worker)

    def _assistant_initialized(self, command: object, error: object) -> None:
        self._initializing = False
        self._remove_initialization_status_card()
        if error is not None or command is None:
            message = str(error or "Не вдалося ініціалізувати асистента.")
            card = self.chat.add_card("Система", message)
            retry = QMessageBox(self)
            retry.setIcon(QMessageBox.Icon.Warning)
            retry.setWindowTitle("Помилка ініціалізації")
            retry.setText(message)
            retry.setStandardButtons(
                QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Close
            )
            if retry.exec() == QMessageBox.StandardButton.Retry:
                self._initialization_status_card = self.chat.add_card(
                    "Система",
                    "Повторна спроба підключення...",
                    status="Ініціалізація",
                )
                self._start_initialization()
            return
        self._command = command
        self._set_commands_enabled(True)

    def send_message(self, text: str, speak_answer: bool = False) -> None:
        text = text.strip()
        if not text:
            return
        if self._initializing:
            self.chat.add_card("Система", "Зачекайте, асистент ще ініціалізується.")
            return
        self._remove_voice_stopped_card()
        self.chat.add_card("Користувач", text, is_user=True)
        if self._command_busy:
            is_cancel_action = getattr(self._command, "is_cancel_action", None)
            if (
                self._command_cancel_event is not None
                and callable(is_cancel_action)
                and is_cancel_action(text)
            ):
                self._command_cancel_event.set()
                interrupt_voice()
                self.chat.add_card("Система", "Скасовую виконання поточної команди...")
            else:
                self._command_queue.append((text, speak_answer))
            return
        self._start_command(text, speak_answer)

    def _start_command(self, text: str, speak_answer: bool = False) -> None:
        self._command_busy = True
        self._command_started_at = time.perf_counter()
        self._command_status_card = self.chat.add_card(
            "System",
            "Виконую запит...",
            status="Виконується · 0.0 мс",
        )
        self._command_timer.start()
        cancel_event = threading.Event()
        self._command_cancel_event = cancel_event
        worker = CommandWorker(
            self._command,
            text,
            speak_answer=speak_answer,
            cancel_event=cancel_event,
        )
        worker.signals.finished.connect(self._command_finished)
        worker.signals.error.connect(self._command_failed)
        worker.signals.model_loading.connect(self._set_model_loading)
        self._thread_pool.start(worker)

    def _set_model_loading(self, loading: bool) -> None:
        if loading:
            if self._model_loading_card is None:
                self._model_loading_card = self.chat.add_card(
                    "Поліна",
                    "",
                    loading=True,
                )
            return
        self.chat.remove_card(self._model_loading_card)
        self._model_loading_card = None

    def _command_finished(self, _text: str, output: object) -> None:
        self.chat.remove_card(self._model_loading_card)
        self._model_loading_card = None
        elapsed = self._stop_command_timer()
        if isinstance(output, dict):
            result = str(output.get("output") or "")
            worker_elapsed = output.get("elapsed")
            if isinstance(worker_elapsed, (int, float)):
                elapsed = max(0.0, float(worker_elapsed))
        else:
            result = str(output or "")

        cancel_requested = (
            self._command_cancel_event is not None
            and self._command_cancel_event.is_set()
        )
        self._command_busy = False
        self._command_cancel_event = None
        if cancel_requested and self._command is not None:
            cancel_pending_action = getattr(self._command, "cancel_pending_action", None)
            if callable(cancel_pending_action):
                cancel_pending_action(silent=True)
            result = "Команду скасовано."
        lines = result.strip().splitlines() if result else []
        lines = [
            line.strip()
            for line in lines
            if line.strip() and not line.strip().startswith("Ви сказали:")
        ]
        if lines:
            self.chat.add_card(
                "Поліна",
                "\n".join(lines),
                status=f"Виконано · {self._format_duration(elapsed)}",
            )
        else:
            self.chat.add_card(
                "Поліна",
                "Команду виконано.",
                status=f"Виконано · {self._format_duration(elapsed)}",
            )
        self._command_queue.clear()
        self._start_next_queued_command()

    @staticmethod
    def _format_duration(elapsed: float) -> str:
        safe_elapsed = max(0.0, elapsed)
        if safe_elapsed < 1.0:
            return f"{safe_elapsed * 1000:.1f} мс"
        return f"{safe_elapsed:.2f} с"

    def _update_command_timer(self) -> None:
        if self._command_started_at is None or self._command_status_card is None:
            return
        elapsed = max(0.0, time.perf_counter() - self._command_started_at)
        self._command_status_card.set_status(
            f"Виконується · {self._format_duration(elapsed)}"
        )

    def _stop_command_timer(self) -> float:
        self._command_timer.stop()
        elapsed = 0.0
        if self._command_started_at is not None:
            elapsed = max(0.0, time.perf_counter() - self._command_started_at)
            self._command_started_at = None
        self.chat.remove_card(self._command_status_card)
        self._command_status_card = None
        return elapsed

    def _command_failed(self, message: str, elapsed: float = 0.0) -> None:
        self.chat.remove_card(self._model_loading_card)
        self._model_loading_card = None
        self._command_busy = False
        self._command_cancel_event = None
        timer_elapsed = self._stop_command_timer()
        final_elapsed = elapsed if elapsed > 0 else timer_elapsed
        self.chat.add_card(
            "Система",
            f"Помилка виконання команди: {message}",
            status=f"Помилка · {self._format_duration(final_elapsed)}",
        )
        self._start_next_queued_command()

    def _start_next_queued_command(self) -> None:
        if self._command_busy or not self._command_queue:
            return
        text, speak_answer = self._command_queue.pop(0)
        self._start_command(text, speak_answer)

    def start_microphone_input(self) -> None:
        if self._initializing:
            self.chat.add_card("Система", "Зачекайте, асистент ще ініціалізується.")
            return
        if self._voice_busy:
            self.stop_microphone_input()
            return
        self._remove_voice_stopped_card()
        self._voice_busy = True
        self.composer.set_microphone_active(True)
        self._voice_status_card = self.chat.add_card(
            "Система",
            "Слухаю вас...",
            status="Запис",
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
        self._voice_stopped_card = self.chat.add_card(
            "Система",
            "Прослуховування мікрофона вимкнено.",
        )

    def _voice_recognized(self, text: str) -> None:
        self._remove_voice_status_card()
        self.send_message(text, speak_answer=True)

    def _voice_failed(self, message: str) -> None:
        self._voice_busy = False
        self._voice_worker = None
        self.composer.set_microphone_active(False)
        self._remove_voice_status_card()
        self.chat.add_card("Система", f"Не вдалося розпізнати голос: {message}")

    def _remove_voice_status_card(self) -> None:
        self.chat.remove_card(self._voice_status_card)
        self._voice_status_card = None

    def _remove_voice_stopped_card(self) -> None:
        self.chat.remove_card(self._voice_stopped_card)
        self._voice_stopped_card = None

    def _remove_initialization_status_card(self) -> None:
        self.chat.remove_card(self._initialization_status_card)
        self._initialization_status_card = None

    def _set_commands_enabled(self, enabled: bool) -> None:
        self.search.setEnabled(enabled)
        self.composer.set_prompt_enabled(enabled)

    def _set_microphone_icon(self, active: bool) -> None:
        self.composer.set_microphone_active(active)
