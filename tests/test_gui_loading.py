import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel

from gui.main_window import CommandWorker, MainWindow
from gui.widgets.chat.chat_widgets import ChatCard, LoadingDot


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def test_model_loading_shows_only_animated_styled_dot(qt_app):
    window = MainWindow(command=object())

    window._set_model_loading(True)

    card = window._model_loading_card
    assert isinstance(card, ChatCard)
    assert card.findChild(LoadingDot) is not None
    assert card.findChild(LoadingDot)._timer.isActive()
    assert card.findChild(QLabel, "messageBody") is None

    window._set_model_loading(False)

    assert window._model_loading_card is None
    window.close()


def test_main_window_initializes_assistant_without_command(qt_app, monkeypatch):
    monkeypatch.setattr("gui.main_window.QThreadPool.start", lambda *_args: None)
    window = MainWindow()

    assert window._initializing
    assert window._initialization_status_card is not None

    command = object()
    window._assistant_initialized(command, None)

    assert window._command is command
    assert not window._initializing
    assert window._initialization_status_card is None
    window.close()


def test_command_worker_forwards_model_loading_state():
    class SemanticAnalyzerStub:
        def __init__(self):
            self.callback = None

        def set_model_loading_callback(self, callback):
            previous_callback = self.callback
            self.callback = callback
            return previous_callback

    semantic_analyzer = SemanticAnalyzerStub()

    class CommandStub:
        response_analyzer = SimpleNamespace(
            decision_engine=SimpleNamespace(
                semantic_analyzer=semantic_analyzer,
            ),
        )

        def process_recognized_command(self, _text):
            self.response_analyzer.decision_engine.semantic_analyzer.callback(True)
            self.response_analyzer.decision_engine.semantic_analyzer.callback(False)

    worker = CommandWorker(CommandStub(), "test")
    loading_states = []
    worker.signals.model_loading.connect(loading_states.append)

    worker.run()

    assert loading_states == [True, False]
    assert semantic_analyzer.callback is None
