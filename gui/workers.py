import json
import threading
from typing import Any, cast
from urllib import request as url_request

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal


class CommandSignals(QObject):
    finished = pyqtSignal(str, object)
    error = pyqtSignal(str)


class VoiceSignals(QObject):
    recognized = pyqtSignal(str)
    error = pyqtSignal(str)


class BackendSignals(QObject):
    finished = pyqtSignal(object, object)


class BackendHealthWorker(QRunnable):
    def __init__(self, backend_url: str) -> None:
        super().__init__()
        self.backend_url = backend_url
        self.signals = BackendSignals()

    def run(self) -> None:
        try:
            with url_request.urlopen(
                f"{self.backend_url}/api/assistant/health/",
                timeout=8,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("ok"):
                self.signals.finished.emit(True, None)
                return
            message = payload.get("message") or "Бекенд асистента недоступний."
            self.signals.finished.emit(False, message)
        except Exception:
            self.signals.finished.emit(
                False,
                "Бекенд асистента недоступний. Запустіть Django у окремому терміналі.",
            )


class CommandWorker(QRunnable):
    def __init__(self, backend_url: str, text: str, speak_answer: bool = False) -> None:
        super().__init__()
        self.backend_url = backend_url
        self.text = text
        self.speak_answer = speak_answer
        self.signals = CommandSignals()

    def run(self) -> None:
        try:
            payload = json.dumps(
                {"text": self.text, "speak_answer": self.speak_answer},
                ensure_ascii=False,
            ).encode("utf-8")
            request = url_request.Request(
                f"{self.backend_url}/api/assistant/command/",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with url_request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
            if not result.get("ok"):
                self.signals.error.emit(
                    result.get("message", "Команду не вдалося виконати.")
                )
                return
            self.signals.finished.emit(self.text, str(result.get("output", "")).strip())
        except Exception:
            self.signals.error.emit("Команду не вдалося виконати. Спробуйте ще раз.")


class VoiceWorker(QRunnable):
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
