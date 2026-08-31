from utils.list_apps import get_list_installed_apps
from django.core.management.base import BaseCommand
import speech_recognition 
from utils.match_app import get_known_apps, find_best_match
import platform, os, subprocess
from utils.voicing_answer import run_voice


class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        self.run = True
        self.stdout.write(self.style.SUCCESS(f"Асистент почав роботу"))

        recognizer = speech_recognition.Recognizer()
        microphone = speech_recognition.Microphone()

        with microphone as source:
            self.stdout.write("Почекайте, йде налаштування мікрофона...")
            recognizer.adjust_for_ambient_noise(source= source)
            self.stdout.write("Слухаю вас...")

            while self.run:
                try:
                    audio = recognizer.listen(source= source, phrase_time_limit= 5)
                    command_text = recognizer.recognize_google(audio, language= "uk-UA")
                    self.stdout.write(f"Ви сказали: {command_text}")
                    self.doing_task(text= command_text)
                    
                except speech_recognition.UnknownValueError:
                    continue
                except Exception as error:
                    self.stdout.write(self.style.WARNING(f"Помилка: {error}"))

    def doing_task(self, text):
        lowered = text.lower()

        if "привіт" in lowered:
            run_voice("Привіт, радa тебе бачити!")
            return

        if "додатки" in lowered:
            run_voice("Відкриваю список додатків...")
            apps = get_list_installed_apps()
            self.stdout.write(f"Встановлені додатки: {', '.join(apps.keys())}")
            return
        
        if "відкрий" in lowered or "закрий" in lowered:
            self.handle_open_close(text= text, is_open= "відкрий" in lowered)
            return

    def handle_open_close(self, text, is_open):
        lowered = text.lower()
        trigger = "відкрий" if is_open else "закрий"

        index = lowered.find(trigger)

        start = index + len(trigger)
        target_word = text[start:].strip()

        if not target_word:
            run_voice("Повторіть яку програму відкрити")
            return 

        apps = get_known_apps()
        name, path = find_best_match(word= target_word, apps= apps, threshold= 0.45)
        if not name:
            run_voice(f"Я не знайшла програму схожу на {target_word}")
            return 
        if is_open:
            run_voice(f"Відкриваю {name}")
            self.open_app(path= path)
        else:
            run_voice(f"Закриваю {name}")
            self.close_app(app_name= os.path.basename(path))
    
    def open_app(self, path):
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(path)
            if system == "Darwin":
                subprocess.Popen(args= ["open", path])
            else:
                subprocess.Popen(args= [path])
        except Exception as error:
            self.stdout.write(self.style.WARNING(f"Помилка закриття: {error}"))

    def close_app(self, app_name: str):
        try:
            system = platform.system()
            if not app_name.endswith(".exe"):
                app_name += ".exe"
            if system == "Windows":
                subprocess.run(
                    args=["taskkill", "/IM", app_name, "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.run(args=["pkill", app_name])
        except Exception as error:
            self.stdout.write(self.style.WARNING(f"Помилка закриття: {error}"))