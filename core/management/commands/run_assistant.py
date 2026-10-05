from typing import Any, cast

from utils.list_apps import get_list_installed_apps
from django.core.management.base import BaseCommand
import speech_recognition
from utils.match_app import get_known_apps, find_best_match
import platform, os, subprocess
from utils.voicing_answer import run_voice, voicing_and_printing_answer
from utils.match_app import register_found_app, is_unknown


CONFIRM_WORDS = ("так", "да", "правильно", "точно", "вірно")
DENY_WORDS = ("ні", "не", "неправильно")

class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        self.run = True
        self.pending_app: dict[str, Any] | None = None

        self.paused = False
        self.stdout.write(self.style.SUCCESS(f"Асистент почав роботу"))
        recognizer = cast(Any, speech_recognition.Recognizer())
        microphone = cast(Any, speech_recognition.Microphone())

        with microphone as source:
            self.stdout.write("Почекайте, йде налаштування мікрофона...")
            recognizer.adjust_for_ambient_noise(source= source)
            self.stdout.write("Слухаю вас...")

            while self.run:
                try:
                    audio = recognizer.listen(source= source, phrase_time_limit= 5)
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
                    continue
                except Exception as error:
                    self.stdout.write(self.style.WARNING(f"Помилка: {error}"))

    def doing_task(self, text):
        lowered = text.strip().lower()

        if self.pending_app:
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

        if "відкрий" in lowered or "закрий" in lowered:
            self.handle_open_close(text= text, is_open= "відкрий" in lowered)
            return

    def handle_confirmation(self, text):
        cleaned_text = text.strip().lower()

        if self.pending_app is None:
            return

        pending_app = self.pending_app

        if cleaned_text in CONFIRM_WORDS:
            register_found_app(
                name=pending_app["name"],
                path=pending_app["path"]
            )

            if pending_app["is_open"]:
                self.open_app(pending_app["path"])
            else:
                self.close_app(
                    os.path.basename(pending_app["path"])
                )

            voicing_and_printing_answer("Добре, запам'ятала")
            self.pending_app = None
            return

        if cleaned_text in DENY_WORDS:
            voicing_and_printing_answer("Тоді спробуй повторити команду ще раз")
            self.pending_app = None
            return

    def pause_assistant(self):
        if self.paused:
            return
        self.paused = True
        run_voice("Асистент на паузі", wait=True)
        self.stdout.write(self.style.WARNING("Асистент на паузі"))

    def resume_assistant(self):
        if not self.paused:
            return
        self.paused = False
        run_voice("Асистент продовжує роботу", wait=True)
        self.stdout.write(self.style.SUCCESS("Асистент продовжив роботу"))

    def stop_assistant(self):
        run_voice("Асистент вимкнений", wait=True)
        self.run = False
        self.paused = False
        self.stdout.write(self.style.WARNING("Асистент зупинено"))

    def handle_open_close(self, text, is_open):
        lowered = text.lower()
        trigger = "відкрий" if is_open else "закрий"

        index = lowered.find(trigger)

        if index == -1:
            voicing_and_printing_answer("Повторіть команду для відкриття або закриття програми")
            return

        start = index + len(trigger)
        target_word = text[start:].strip()

        if not target_word:
            voicing_and_printing_answer("Повторіть яку програму відкрити")
            return

        voicing_and_printing_answer("Починаю шукати програму...")
        apps = get_known_apps()
        match_result = find_best_match(word=target_word, apps=apps, threshold=0.45)

        if match_result is None:
            voicing_and_printing_answer(f"Я не знайшла програму схожу на {target_word}")
            return

        name, path = match_result

        if not name or not path:
            voicing_and_printing_answer(f"Я не знайшла програму схожу на {target_word}")
            return

        is_unknown_app = is_unknown(name=name, path=path)

        if is_unknown_app:
            voicing_and_printing_answer(f"Чи правильно я почув назву? Назва програми: {name}?")
            self.pending_app = {
                "name": name,
                "path": path,
                "is_open": is_open,
            }
            return

        voicing_and_printing_answer(f"Знайшла програму {name}")

        if is_open:
            voicing_and_printing_answer(f"Відкриваю {name}")
            register_found_app(name=name, path=path)
            self.open_app(path=path)
        else:
            voicing_and_printing_answer(f"Закриваю {name}")
            register_found_app(name=name, path=path)
            self.close_app(app_name=os.path.basename(path))

    def open_app(self, path):
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(path)
            elif system == "Darwin":
                subprocess.Popen(args=["open", path])
            else:
                subprocess.Popen(args=[path])
        except Exception as error:
            self.stdout.write(self.style.WARNING(f"Помилка відкриття: {error}"))

    def close_app(self, app_name: str):
        try:
            system = platform.system()
            app_name = os.path.basename(app_name)
            if system == "Windows" and not app_name.lower().endswith(".exe"):
                app_name += ".exe"
            if system == "Windows":
                subprocess.run(
                    args=["taskkill", "/IM", app_name, "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.run(args=["pkill", "-f", app_name])
        except Exception as error:
            self.stdout.write(self.style.WARNING(f"Помилка закриття: {error}"))