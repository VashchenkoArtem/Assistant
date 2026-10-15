from typing import Any, cast
import re

from utils.list_apps import get_list_installed_apps
from django.core.management.base import BaseCommand
import speech_recognition
from utils.match_app import get_known_apps, find_best_match
import platform, os, subprocess
from utils.voicing_answer import run_voice, voicing_and_printing_answer, voicing_text
from utils.match_app import register_found_app, is_unknown
from core.models import AppCommand
from utils.voicing_answer import (
    AUDIO_LOCK,
    VOICE_ACTIVE,
    run_voice,
    voicing_and_printing_answer,
)
from utils.match_app import register_found_app, is_unknown
from core.response_analysis import (
    DialogContext,
    DialogState,
    ResponseAnalyzer,
    ResponseCandidate,
    ResponseCategory,
    ResponseLearner,
    ResponseRepository,
    ResponseSource,
)


CONFIRM_WORDS = ("так", "да", "правильно", "точно", "вірно", "так так", "ага")
DENY_WORDS = ("ні", "не", "неправильно", "ні ні", "нет")
CANCEL_ACTION_WORDS = ("скасуй", "скасувати", "скасовую", "відміна", "відміни", "відмінити")
APP_COMMAND_PATTERN = re.compile(
    r"\b(?P<verb>відкрий|відкрити|відкривай|відкривати|"
    r"закрий|закрити|закривай|закривати)\b",
    re.IGNORECASE,
)
GENERIC_APP_PREFIX = re.compile(
    r"^(?:програму|програма|програми|додаток|додатки|застосунок|застосунки)\b\s*",
    re.IGNORECASE,
)

class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        self.run = True
        self.pending_app: dict[str, Any] | None = None
        self.pending_learning_candidate: ResponseCandidate | None = None
        self.response_repository = ResponseRepository("sqlite:///response_patterns.db")
        self.response_analyzer = ResponseAnalyzer(self.response_repository)
        self.response_learner = ResponseLearner(self.response_repository)

        self.paused = False
        self.stdout.write(self.style.SUCCESS(f"Асистент почав роботу"))
        recognizer = cast(Any, speech_recognition.Recognizer())
        microphone = cast(Any, speech_recognition.Microphone())

        # === ЧУТЛИВІ НАЛАШТУВАННЯ МІКРОФОНА ===
        recognizer.energy_threshold = 100           
        recognizer.dynamic_energy_threshold = False  
        recognizer.phrase_threshold = 0.0           
        recognizer.pause_threshold = 0.5            
        recognizer.non_speaking_duration = 0.4      
        # ==========================================================

        with microphone as source:
            self.stdout.write("Слухаю вас...")

            while self.run:
                try:
                    audio = self.listen_for_audio(recognizer, source)
                    if audio is None:
                        continue

                    command_text = recognizer.recognize_google(audio, language= "uk-UA")
                    self.stdout.write(f"Ви сказали: {command_text}")

                    if self.paused:
                        if any(keyword in command_text.lower() for keyword in ["продовж", "продовжуй", "продовжи", "віднови"]):
                            self.resume_assistant()
                        elif any(keyword in command_text.lower() for keyword in ["зупини", "стоп", "вимкни", "вимкнись"]):
                            self.stop_assistant()
                        continue

                    self.doing_task(text= command_text)

                except speech_recognition.UnknownValueError:
                    # Якщо мікрофон не розібрав звук, ми просто просимо повторити, а не вибираємо "ні" за вас
                    if self.pending_app:
                        self.stdout.write("Не розібрав звук. Будь ласка, повторіть: так або ні.")
                    continue
                except speech_recognition.WaitTimeoutError:
                    continue
                except Exception as error:
                    self.stdout.write(self.style.WARNING(f"Помилка: {error}"))

    @staticmethod
    def listen_for_audio(recognizer: Any, source: Any):
        with AUDIO_LOCK:
            if VOICE_ACTIVE.is_set():
                return None

            try:
                audio = recognizer.listen(
                    source=source,
                    timeout=1,
                    phrase_time_limit=5,
                )
            except speech_recognition.WaitTimeoutError:
                return None

            if VOICE_ACTIVE.is_set():
                return None
            return audio

    def handle_open_close(self, text: str, is_open: bool):
        clean_name = APP_COMMAND_PATTERN.sub("", text).strip()
        clean_name = GENERIC_APP_PREFIX.sub("", clean_name).strip()

        if not clean_name:
            voicing_and_printing_answer("Яку саме програму ви хочете запустити?")
            return

        self.pending_app = {
            "name": clean_name,
            "is_open": is_open,
            "awaiting_name": False
        }

        voicing_and_printing_answer(f"Чи правильно я почув назву? Назва програми: {clean_name}?")

    def handle_app_name_correction(self, text: str):
        if not self.pending_app:
            return
        
        clean_name = text.strip()
        if clean_name.lower() in DENY_WORDS or clean_name.lower() in CANCEL_ACTION_WORDS:
            self.cancel_pending_action()
            return

        self.pending_app["name"] = clean_name
        self.pending_app["awaiting_name"] = False
        voicing_and_printing_answer(f"Добре, шукаю виправлену назву. Назва програми: {clean_name}?")

    def handle_learning_confirmation(self, text: str):
        self.pending_learning_candidate = None
        voicing_and_printing_answer("Добре, я запам'ятала цю команду.")

    def stop_assistant(self):
        self.run = False
        voicing_and_printing_answer("Завершую роботу. До побачення!")

    def pause_assistant(self):
        self.paused = True
        voicing_and_printing_answer("Роботу призупинено.")

    def resume_assistant(self):
        self.paused = False
        voicing_and_printing_answer("Слухаю вас, роботу відновлено.")

    def doing_task(self, text):
        lowered = text.strip().lower()

        if self.pending_app and self.is_cancel_action(lowered):
            self.cancel_pending_action()
            return

        if self.pending_learning_candidate is not None:
            self.handle_learning_confirmation(lowered)
            return

        if self.pending_app:
            if self.pending_app.get("awaiting_name"):
                self.handle_app_name_correction(text)
                return
            self.handle_confirmation(lowered)
            return
        if any(keyword in lowered for keyword in ["пауза"]):
            self.pause_assistant()
            return

        if any(keyword in lowered for keyword in ["продовж", "віднови"]):
            self.resume_assistant()
            return

        if any(keyword in lowered for keyword in ["зупини", "стоп", "вимкни"]):
            self.stop_assistant()
            return

        if "привіт" in lowered:
            voicing_and_printing_answer("Привіт, рада тебе бачити!")
            return

        if "додатки" in lowered:
            voicing_and_printing_answer("Відкриваю список додатків...")
            apps = get_list_installed_apps()
            self.stdout.write(f"Встановлені додатки: {', '.join(apps.keys())}")
            return

        if APP_COMMAND_PATTERN.search(lowered):
            match = APP_COMMAND_PATTERN.search(text)
            if match is not None:
                is_open = not match.group("verb").lower().startswith("закри")
                self.handle_open_close(text=text, is_open=is_open)
            return

    @staticmethod
    def is_cancel_action(text):
        normalized = re.sub(r"[^\w\s]", "", text.lower()).strip()
        if not normalized:
            return False
        first_word = normalized.split(maxsplit=1)[0]
        return first_word in CANCEL_ACTION_WORDS

    def cancel_pending_action(self):
        pending_app = self.pending_app
        self.pending_app = None
        self.pending_learning_candidate = None

        if pending_app is None:
            return

        action = "відкриття" if pending_app["is_open"] else "закриття"
        voicing_and_printing_answer(
            f"Добре, скасувала {action} програми {pending_app.get('name', '')}."
        )

    def analyze_response(self, text, question=""):
        context = DialogContext(
            state=DialogState.WAITING_FOR_RESPONSE,
            question=question,
            pending_action="add_or_close_app" if self.pending_app else "",
            expected_response_categories=(ResponseCategory.CONFIRMATION, ResponseCategory.REJECTION),
        )
        return self.response_analyzer.analyze(question, text, context)

    def handle_confirmation(self, text):
        cleaned_text = text.strip().lower()

        if self.pending_app is None:
            return

        pending_app = self.pending_app
        question = f"Чи правильно я почув назву? Назва програми: {pending_app['name']}?"
        analysis = self.analyze_response(cleaned_text, question=question)

        if (
            analysis.category == ResponseCategory.UNKNOWN
            and cleaned_text not in CONFIRM_WORDS
            and cleaned_text not in DENY_WORDS
        ):
            voicing_and_printing_answer(
                f"Не впевнена, чи правильно зрозуміла. {question} Відповідь: так або ні."
            )
            return

        if analysis.category == ResponseCategory.REJECTION or cleaned_text in DENY_WORDS:
            pending_app["awaiting_name"] = True
            voicing_and_printing_answer(
                "Добре, це не та програма. Назвіть її точну назву."
            )
            return

        if analysis.category == ResponseCategory.CONFIRMATION or cleaned_text in CONFIRM_WORDS:
            # Сюди допишеться реальний запуск додатка (наприклад, запуск процесу)
            voicing_and_printing_answer(f"Добре, запускаю програму {pending_app['name']}.")
