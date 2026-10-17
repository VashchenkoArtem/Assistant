from typing import Any, cast
import re

from utils.list_apps import get_list_installed_apps
from django.core.management.base import BaseCommand
import speech_recognition
from utils.match_app import (
    find_exact_match,
    find_similar_apps,
    get_app_open_counts,
    get_known_apps,
    sync_installed_apps,
)
import platform, os, subprocess
from utils.match_app import increment_open_count, register_found_app, is_unknown
from utils.voicing_answer import (
    AUDIO_LOCK,
    VOICE_ACTIVE,
    run_voice,
    voicing_and_printing_answer,
)
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
        self.response_repository = ResponseRepository()
        self.response_analyzer = ResponseAnalyzer(self.response_repository)
        self.response_learner = ResponseLearner(self.response_repository)

        self.paused = False
        synced_apps = sync_installed_apps()
        self.stdout.write(f"Збережено знайдені програми: {synced_apps}")
        self.stdout.write(self.style.SUCCESS(f"Асистент почав роботу"))
        recognizer = cast(Any, speech_recognition.Recognizer())
        microphone = cast(Any, speech_recognition.Microphone())

        with microphone as source:
            self.configure_recognizer(recognizer, source)
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
                    
                    if self.pending_app:
                        self.stdout.write("Не розібрав звук. Будь ласка, повторіть: так або ні.")
                    continue
                except speech_recognition.WaitTimeoutError:
                    continue
                except Exception as error:
                    self.stdout.write(self.style.WARNING(f"Помилка: {error}"))

    @staticmethod
    def configure_recognizer(recognizer: Any, source: Any) -> None:
        recognizer.dynamic_energy_threshold = True
        recognizer.adjust_for_ambient_noise(source, duration=1)
        recognizer.phrase_threshold = 0.15
        recognizer.pause_threshold = 0.8
        recognizer.non_speaking_duration = 0.5

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

    def doing_task(self, text):
        lowered = text.strip().lower()

        if self.pending_app and self.is_cancel_action(lowered):
            self.cancel_pending_action()
            return

        if self.pending_learning_candidate is not None:
            self.handle_learning_confirmation(lowered)
            return

        if self.pending_app:
            if self.pending_app.get("awaiting_selection"):
                self.handle_app_selection(text)
                return
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

        if analysis.category == ResponseCategory.UNKNOWN:
            voicing_and_printing_answer(
                f"Не впевнена, чи правильно зрозуміла. {question} Відповідь: так або ні."
            )
            return

        self.response_repository.record_decision(
            response=cleaned_text,
            category=analysis.category,
            context=question,
            candidate=pending_app["name"],
            confidence=analysis.confidence,
        )

        if analysis.category == ResponseCategory.REJECTION:
            if analysis.source == ResponseSource.SEMANTIC:
                candidate = self.response_learner.create_candidate(
                    text=cleaned_text,
                    category=analysis.category,
                    confidence=analysis.confidence,
                )
                if candidate is not None:
                    self.pending_learning_candidate = candidate
                    voicing_and_printing_answer(
                        f"Запам'ятати фразу «{candidate.text}» як відмову? Скажіть так або ні."
                    )
                    return

            pending_app["awaiting_name"] = True
            voicing_and_printing_answer(
                "Добре, це не та програма. Назвіть її точну назву."
            )
            return

        if analysis.source == ResponseSource.SEMANTIC:
            candidate = self.response_learner.create_candidate(
                text=cleaned_text,
                category=analysis.category,
                confidence=analysis.confidence,
            )
            if candidate is not None:
                self.pending_learning_candidate = candidate
                category_label = (
                    "підтвердження"
                    if candidate.category == ResponseCategory.CONFIRMATION
                    else "відмову"
                )
                voicing_and_printing_answer(
                    f"Запам'ятати фразу «{candidate.text}» як {category_label}? Скажіть так або ні."
                )
                return

        self._complete_pending_app()

    def handle_app_name_correction(self, text):
        pending_app = self.pending_app
        if pending_app is None:
            return

        corrected_name = text.strip()
        if not corrected_name:
            voicing_and_printing_answer("Назвіть точну назву програми.")
            return

        is_open = pending_app["is_open"]
        self.pending_app = None
        command = "відкрий" if is_open else "закрий"
        self.handle_open_close(f"{command} {corrected_name}", is_open=is_open)

    def handle_learning_confirmation(self, text):
        candidate = self.pending_learning_candidate
        if candidate is None:
            return

        question = (
            f"Запам'ятати фразу «{candidate.text}»? "
            "Скажіть так або ні."
        )
        analysis = self.analyze_response(text, question=question)

        if analysis.category == ResponseCategory.UNKNOWN:
            voicing_and_printing_answer(
                f"Не впевнена, чи запам'ятовувати цю фразу. {question}"
            )
            return

        self.response_repository.record_decision(
            response=text,
            category=analysis.category,
            context=question,
            candidate=candidate.text,
            confidence=analysis.confidence,
        )
        if analysis.category == ResponseCategory.CONFIRMATION:
            self.response_learner.accept_candidate(candidate)
            voicing_and_printing_answer(f"Запам'ятала фразу «{candidate.text}».")
        else:
            self.response_learner.reject_candidate(candidate)
            voicing_and_printing_answer("Добре, не буду її запам'ятовувати.")

        self.pending_learning_candidate = None
        if candidate.category == ResponseCategory.REJECTION:
            if self.pending_app is not None:
                self.pending_app["awaiting_name"] = True
            voicing_and_printing_answer("Назвіть точну назву програми.")
            return

        self._complete_pending_app()

    def _complete_pending_app(self):
        pending_app = self.pending_app
        if pending_app is None:
            return

        command = register_found_app(
            name=pending_app["name"],
            path=pending_app["path"],
        )

        if pending_app["is_open"]:
            if self.open_app(pending_app["path"]):
                increment_open_count(command)
        else:
            app_path = pending_app["path"]
            self.close_app(
                app_path if app_path.startswith("appx://") else os.path.basename(app_path)
            )

        self.pending_app = None

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
        match = APP_COMMAND_PATTERN.search(text)
        if match is None:
            voicing_and_printing_answer("Повторіть команду для відкриття або закриття програми")
            return

        target_word = text[match.end():].strip(" \t.,!?")
        target_word = GENERIC_APP_PREFIX.sub("", target_word).strip(" \t.,!?")

        if not target_word:
            action = "відкрити" if is_open else "закрити"
            self.pending_app = {
                "is_open": is_open,
                "awaiting_name": True,
            }
            voicing_and_printing_answer(f"Яку програму {action}? Назвіть її.")
            return

        voicing_and_printing_answer("Починаю шукати програму...")
        apps = get_known_apps()
        open_counts = get_app_open_counts(apps.keys())
        exact_match = find_exact_match(
            word=target_word,
            apps=apps,
            open_counts=open_counts,
        )

        if exact_match is None:
            suggestions = find_similar_apps(
                word=target_word,
                apps=apps,
                threshold=0.45,
                open_counts=open_counts,
            )
            if not suggestions:
                voicing_and_printing_answer(
                    f"Я не знайшла програму схожу на {target_word}"
                )
                return

            self.pending_app = {
                "awaiting_selection": True,
                "suggestions": suggestions,
                "is_open": is_open,
            }
            options = "; ".join(
                f"{index}. {name}"
                for index, (name, _path) in enumerate(suggestions, start=1)
            )
            self.stdout.write(f"Схожі програми: {options}")
            run_voice("Ось програми.")
            return

        name, path = exact_match

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
        self.execute_app_action(name, path, is_open)

    def handle_app_selection(self, text: str) -> None:
        pending_app = self.pending_app
        if pending_app is None:
            return

        suggestions = pending_app["suggestions"]
        normalized_text = re.sub(r"[^\w\s]", "", text.lower()).strip()
        ordinal_indices = {
            "перший": 0,
            "перша": 0,
            "перше": 0,
            "другий": 1,
            "друга": 1,
            "друге": 1,
            "третій": 2,
            "третя": 2,
            "третє": 2,
            "четвертий": 3,
            "четверта": 3,
            "четверте": 3,
            "пятий": 4,
            "пята": 4,
            "пяте": 4,
            "п'ятий": 4,
            "п'ята": 4,
            "п'яте": 4,
        }
        selected_index = ordinal_indices.get(normalized_text)
        if selected_index is None and normalized_text.isdigit():
            selected_index = int(normalized_text) - 1

        if selected_index is not None and 0 <= selected_index < len(suggestions):
            name, path = suggestions[selected_index]
        else:
            exact_match = find_exact_match(
                text,
                dict(suggestions),
                get_app_open_counts(name for name, _path in suggestions),
            )
            if exact_match is None:
                voicing_and_printing_answer(
                    "Не розпізнала вибір. Назвіть номер однієї з програм у списку "
                    "або скасуйте дію."
                )
                return
            name, path = exact_match

        is_open = pending_app["is_open"]
        self.pending_app = None
        voicing_and_printing_answer(f"Вибрано програму {name}.")
        self.execute_app_action(name, path, is_open)

    def execute_app_action(self, name: str, path: str, is_open: bool) -> None:
        command = register_found_app(name=name, path=path)
        if is_open:
            voicing_and_printing_answer(f"Відкриваю {name}")
            if self.open_app(path=path):
                increment_open_count(command)
        else:
            voicing_and_printing_answer(f"Закриваю {name}")
            self.close_app(
                app_name=path if path.startswith("appx://") else os.path.basename(path)
            )

    def open_app(self, path) -> bool:
        try:
            system = platform.system()
            if system == "Windows":
                if path.startswith("appx://"):
                    app_id, _, _ = path.removeprefix("appx://").partition("|")
                    os.startfile(f"shell:AppsFolder\\{app_id}")
                else:
                    os.startfile(path)
            elif system == "Darwin":
                subprocess.Popen(args=["open", path])
            else:
                subprocess.Popen(args=[path])
        except Exception as error:
            self.stdout.write(self.style.WARNING(f"Помилка відкриття: {error}"))
            return False
        return True

    def close_app(self, app_name: str):
        try:
            system = platform.system()
            if system == "Windows" and app_name.startswith("appx://"):
                app_id = app_name.removeprefix("appx://")
                package_family = app_id.partition("!")[0]
                if not package_family:
                    raise ValueError("Не вдалося визначити пакет Microsoft Store програми")

                result = subprocess.run(
                    args=[
                        "powershell",
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        (
                            "$package = Get-AppxPackage | "
                            "Where-Object PackageFamilyName -eq "
                            "$env:ASSISTANT_PACKAGE_FAMILY | Select-Object -First 1; "
                            "if (-not $package) { exit 2 }; "
                            "$prefix = $package.InstallLocation.TrimEnd('\\') + '\\'; "
                            "$processIds = Get-CimInstance Win32_Process | "
                            "Where-Object { $_.ExecutablePath -and "
                            "$_.ExecutablePath.StartsWith($prefix, "
                            "[StringComparison]::OrdinalIgnoreCase) } | "
                            "Select-Object -ExpandProperty ProcessId; "
                            "foreach ($processId in $processIds) { "
                            "Stop-Process -Id $processId -Force -ErrorAction Stop }"
                        ),
                    ],
                    env={**os.environ, "ASSISTANT_PACKAGE_FAMILY": package_family},
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                if result.returncode != 0:
                    message = result.stderr.strip() or "Пакет Microsoft Store не знайдено"
                    self.stdout.write(
                        self.style.WARNING(f"Не вдалося закрити Store-програму: {message}")
                    )
                return
            else:
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
