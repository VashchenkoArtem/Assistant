import os
import threading
from unittest.mock import Mock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from gui.main_window import CommandWorker, MainWindow


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


class CancelCommand:
    def __init__(self):
        self.pending_app = None
        self.pending_file = None
        self.pending_learning_candidate = None

    @staticmethod
    def is_cancel_action(text: str) -> bool:
        return text.strip().casefold() == "скасувати"

    def cancel_pending_action(self, silent: bool = False) -> None:
        _ = silent
        self.pending_app = None
        self.pending_file = None
        self.pending_learning_candidate = None


def test_cancel_message_interrupts_busy_gui_command(qt_app):
    window = MainWindow(command=CancelCommand())
    cancel_event = threading.Event()
    window._command_busy = True
    window._command_cancel_event = cancel_event

    with patch("gui.main_window.interrupt_voice") as interrupt_voice:
        window.send_message("скасувати")

    assert cancel_event.is_set()
    interrupt_voice.assert_called_once_with()
    assert window._command_busy
    window.close()


def test_cancelled_worker_does_not_start_command_and_reports_cancellation():
    command = Mock()
    cancel_event = threading.Event()
    cancel_event.set()
    worker = CommandWorker(command, "довга команда", cancel_event=cancel_event)
    outputs = []
    worker.signals.finished.connect(lambda _text, output: outputs.append(output))

    worker.run()

    command.process_recognized_command.assert_not_called()
    assert outputs == ["Команду скасовано."]


def test_worker_reports_elapsed_time(monkeypatch):
    class TimedCommand:
        def process_recognized_command(self, text):
            print(f"processed {text}")

    times = iter((1.0, 1.375))
    monkeypatch.setattr("gui.workers.time.perf_counter", lambda: next(times))
    worker = CommandWorker(TimedCommand(), "command")
    results = []
    worker.signals.finished.connect(
        lambda text, payload: results.append((text, payload))
    )

    worker.run()

    assert results == [
        ("command", {"output": "processed command", "elapsed": 0.375})
    ]


def test_finished_command_displays_worker_elapsed_time(qt_app):
    window = MainWindow(command=CancelCommand())
    with patch.object(window.chat, "add_card", wraps=window.chat.add_card) as add_card:
        window._command_finished(
            "command",
            {"output": "done", "elapsed": 0.25},
        )

    add_card.assert_called_once_with(
        "Поліна",
        "done",
        status="Виконано · 250.0 мс",
    )
    window.close()


def test_finished_command_without_output_still_displays_elapsed_time(qt_app):
    window = MainWindow(command=CancelCommand())
    with patch.object(window.chat, "add_card", wraps=window.chat.add_card) as add_card:
        window._command_finished(
            "command",
            {"output": "", "elapsed": 0.125},
        )

    add_card.assert_called_once_with(
        "Поліна",
        "Команду виконано.",
        status="Виконано · 125.0 мс",
    )
    window.close()


def test_cancel_requested_as_command_finishes_clears_pending_action(qt_app):
    command = CancelCommand()
    command.pending_file = {"awaiting_target": True}
    window = MainWindow(command=command)
    window._command_busy = True
    window._command_cancel_event = threading.Event()
    window._command_cancel_event.set()

    window._command_finished("Знайди файл", "Вкажіть назву файла.")

    assert command.pending_file is None
    assert not window._command_busy
    window.close()
