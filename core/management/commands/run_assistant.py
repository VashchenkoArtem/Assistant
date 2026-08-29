from utils.list_apps import get_list_installed_apps
from django.core.management.base import BaseCommand
import speech_recognition 

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
            self.stdout.write("Привіт, радий тебе бачити!")
        if "додатки" in lowered:
            self.stdout.write("Відкриваю список додатків...")
            apps = get_list_installed_apps()
            self.stdout.write(f"Встановлені додатки: {', '.join(apps.keys())}")