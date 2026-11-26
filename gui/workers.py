import contextlib
import io
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, cast

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from utils.audio_settings import get_microphone_device_index
from utils.voicing_answer import (
    GUI_TEXT_MODE,
    PHRASE_TIME_LIMIT,
    configure_recognizer,
    listen_for_audio,
)


class CommandSignals(QObject):
    finished = pyqtSignal(str, object)
    error = pyqtSignal(str, float)
    model_loading = pyqtSignal(bool)


class VoiceSignals(QObject):
    recognized = pyqtSignal(str)
    error = pyqtSignal(str)


class InitializationSignals(QObject):
    finished = pyqtSignal(object, object)


class InitializationWorker(QRunnable):
    def __init__(self, project_root: Path) -> None:
        super().__init__()
        self.project_root = project_root
        self.signals = InitializationSignals()
        self.result_command: object | None = None
        self.result_error: object | None = None

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
            message = "Метод initialize_for_text() не знайдено."
            self.result_error = message
            self.signals.finished.emit(None, message)
        except Exception as error:
            self.result_error = str(error)
            self.signals.finished.emit(None, str(error))


class CommandWorker(QRunnable):
    def __init__(
        self,
        command: Any,
        text: str,
        speak_answer: bool = False,
        cancel_event: threading.Event | None = None,
    ) -> None:
        super().__init__()
        self.command = command
        self.text = text
        self.speak_answer = speak_answer
        self.cancel_event = cancel_event if cancel_event is not None else threading.Event()
        self.signals = CommandSignals()

    def run(self) -> None:
        if self.cancel_event.is_set():
            self.signals.finished.emit(self.text, "Команду скасовано.")
            return

        started_at = time.perf_counter()
        buffer = io.StringIO()
        semantic_analyzer = getattr(
            getattr(getattr(self.command, "response_analyzer", None), "decision_engine", None),
            "semantic_analyzer",
            None,
        )
        set_loading_callback = getattr(semantic_analyzer, "set_model_loading_callback", None)
        previous_loading_callback = (
            set_loading_callback(self.signals.model_loading.emit)
            if callable(set_loading_callback)
            else None
        )
        try:
            from django.core.management.base import OutputWrapper

            self.command.stdout = OutputWrapper(buffer)
            self.command.cancel_event = self.cancel_event
            if not self.speak_answer:
                GUI_TEXT_MODE.set()
            else:
                GUI_TEXT_MODE.clear()
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                try:
                    if self.cancel_event.is_set():
                        raise InterruptedError
                    self.command.process_recognized_command(self.text)
                except InterruptedError:
                    print("Команду скасовано.")
            output = buffer.getvalue().strip()
            elapsed = max(0.0, time.perf_counter() - started_at)
            self.signals.finished.emit(
                self.text,
                {"output": output, "elapsed": elapsed},
            )
        except Exception as error:
            elapsed = max(0.0, time.perf_counter() - started_at)
            self.signals.error.emit(str(error), elapsed)
        finally:
            if callable(set_loading_callback):
                set_loading_callback(previous_loading_callback)
            GUI_TEXT_MODE.clear()


class VoiceWorker(QRunnable):
    def __init__(self, phrase_time_limit: float = PHRASE_TIME_LIMIT) -> None:
        super().__init__()
        self.phrase_time_limit = phrase_time_limit
        self.signals = VoiceSignals()
        self.stop_event = threading.Event()

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        try:
            import speech_recognition

            recognizer = cast(Any, speech_recognition.Recognizer())
            microphone = cast(
                Any,
                speech_recognition.Microphone(
                    device_index=get_microphone_device_index()
                ),
            )
            with microphone as source:
                configure_recognizer(recognizer, source)
                while not self.stop_event.is_set():
                    try:
                        audio = listen_for_audio(
                            recognizer,
                            source,
                            self.phrase_time_limit,
                        )
                        if audio is None:
                            continue
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
