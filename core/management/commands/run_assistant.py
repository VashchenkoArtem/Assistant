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
    VOICE_ACTIVE,
    interrupt_voice,
    run_voice,
    voicing_and_printing_answer,
)
from utils.file_explorer import (
    close_explorer_tab,
    close_explorer_windows,
    find_open_explorer_folders,
    find_file_targets,
    find_file_targets_in_folder,
    find_similar_file_targets,
    get_active_explorer_path,
    get_active_explorer_subfolders,
    is_current_folder_request,
    navigate_explorer_back,
    navigate_explorer_to,
    open_target,
    parse_open_target_command,
)
from utils.text_similarity import similarity
from utils.transliterate import transliterate
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
CLOSE_EXPLORER_PATTERN = re.compile(
    r"\b(?:закрий|закрити|закривай|закривати|закриття)\b.*"
    r"\b(?:провідник|провідника|explorer|file\s+explorer)\b",
    re.IGNORECASE,
)
CLOSE_FOLDER_PATTERN = re.compile(
    r"\b(?:закрий|закрити|закривай|закривати)\s+"
    r"(?:папку|каталог|директорію)\s+(?P<name>.+)$",
    re.IGNORECASE,
)
NAVIGATE_BACK_PATTERN = re.compile(
    r"\b(?:назад(?:\s+(?:у|в)\s+провіднику|\s+по\s+папках)?|"
    r"попередню\s+папку|перейти\s+назад\s+по\s+папках)\b",
    re.IGNORECASE,
)
NAVIGATE_FORWARD_PATTERN = re.compile(
    r"\b(?:вперед(?:\s+(?:у|в)\s+провіднику|\s+по\s+папках)?|"
    r"перейти\s+вперед\s+по\s+папках|"
    r"далі(?:\s+(?:у|в)\s+провіднику|\s+по\s+папках)?)\b",
    re.IGNORECASE,
)
GENERIC_APP_PREFIX = re.compile(
    r"^(?:програму|програма|програми|додаток|додатки|застосунок|застосунки)\b\s*",
    re.IGNORECASE,
)
SELECTION_NUMBER_WORDS = {
    1: (
        "один", "одна", "одне", "одну", "перший", "перша", "перше",
        "першу", "первый", "первая", "первое",
    ),
    2: ("два", "дві", "двох", "другий", "друга", "друге", "второй", "вторая", "второе"),
    3: ("три", "трьох", "третій", "третя", "третє", "третий", "третья", "третье"),
    4: ("чотири", "чотирьох", "четвертий", "четверта", "четверте", "четвертый", "четвертая"),
    5: (
        "п'ять", "пять", "п'ятьох", "пятьох", "п'ятий", "пятий", "п'ята", "пята",
        "п'яте", "пяте", "пятый", "пятая",
    ),
    6: ("шість", "шесть", "шостий", "шоста", "шосте", "шестой", "шестая"),
    7: ("сім", "сімох", "семь", "сьомий", "сьома", "седьмой", "седьмая"),
    8: ("вісім", "восьми", "восемь", "восьмий", "восьма", "восьме", "восьмой", "восьмая"),
    9: ("дев'ять", "девять", "дев'ятий", "девятий", "дев'ята", "девята", "девятый"),
    10: ("десять", "десятий", "десята", "десяте", "десятый", "десятая"),
}
SELECTION_WORD_TO_NUMBER = {
    word: number
    for number, words in SELECTION_NUMBER_WORDS.items()
    for word in words
}

class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        self.run = True
        self.pending_app: dict[str, Any] | None = None
        self.pending_file: dict[str, Any] | None = None
        self.unrecognized_audio_prompted = False
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
                    self.process_recognized_command(command_text)

                except speech_recognition.UnknownValueError:
                    self.handle_unrecognized_audio()
                    continue
                except speech_recognition.WaitTimeoutError:
                    continue
                except Exception as error:
                    self.stdout.write(self.style.WARNING(f"Помилка: {error}"))

    @staticmethod
    def configure_recognizer(recognizer: Any, source: Any) -> None:
        recognizer.dynamic_energy_threshold = True
        recognizer.adjust_for_ambient_noise(source, duration=1)
        recognizer.phrase_threshold = 0.05
        recognizer.pause_threshold = 0.6
        recognizer.non_speaking_duration = 0.25

    @staticmethod
    def listen_for_audio(recognizer: Any, source: Any):
        try:
            return recognizer.listen(
                source=source,
                timeout=1,
                phrase_time_limit=5,
            )
        except speech_recognition.WaitTimeoutError:
            return None

    def doing_task(self, text):
        lowered = text.strip().lower()

        if (
            (self.pending_app or getattr(self, "pending_file", None))
            and self.is_cancel_action(lowered)
        ):
            self.cancel_pending_action()
            return

        pending_file = getattr(self, "pending_file", None)
        if pending_file and NAVIGATE_BACK_PATTERN.search(lowered):
            self.pending_file = None
            self.navigate_explorer_back()
            return

        if self.pending_learning_candidate is not None:
            self.handle_learning_confirmation(lowered)
            return

        if self.pending_app:
            if self.pending_app.get("awaiting_selection"):
                self.handle_app_selection(text)
                return
            if self.pending_app.get("awaiting_selection_confirmation"):
                self.handle_app_selection_confirmation(lowered)
                return
            if self.pending_app.get("awaiting_name"):
                self.handle_app_name_correction(text)
                return
            self.handle_confirmation(lowered)
            return
        pending_file = getattr(self, "pending_file", None)
        if pending_file:
            if pending_file.get("awaiting_explorer_close_selection"):
                self.handle_explorer_close_selection(text)
                return
            if pending_file.get("awaiting_selection"):
                self.handle_file_selection(text)
                return
            if pending_file.get("awaiting_selection_confirmation"):
                self.handle_file_selection_confirmation(lowered)
                return
            if pending_file.get("awaiting_target"):
                self.pending_file = None
                self.handle_file_open(
                    pending_file["kind"],
                    text,
                    new_window=pending_file.get("new_window", False),
                    current_folder=pending_file.get("current_folder", False),
                )
                return
            if pending_file.get("awaiting_explorer_folder_name"):
                self.handle_explorer_folder_name(text)
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

        # Убрал озвучивание
        if "додатки" in lowered:
            self.stdout.write("Отримую список додатків...")
            apps = get_list_installed_apps()
            self.stdout.write(f"Встановлені додатки: {', '.join(apps.keys())}")
            return

        if CLOSE_EXPLORER_PATTERN.search(lowered):
            self.close_explorer()
            return

        close_folder_match = CLOSE_FOLDER_PATTERN.search(text)
        if close_folder_match is not None:
            self.close_explorer_folder(close_folder_match.group("name"))
            return

        if NAVIGATE_BACK_PATTERN.search(lowered):
            self.navigate_explorer_back()
            return

        forward_match = NAVIGATE_FORWARD_PATTERN.search(lowered)
        if forward_match:
            requested_name = text[forward_match.end():].strip(" \t.,!?;:")
            self.navigate_explorer_forward(requested_name=requested_name)
            return

        target_command = parse_open_target_command(text)
        if target_command is not None:
            kind, target, new_window = target_command
            self.handle_file_open(
                kind,
                target,
                new_window=new_window,
                current_folder=(
                    kind == "file" and is_current_folder_request(text)
                ),
            )
            return

        if APP_COMMAND_PATTERN.search(lowered):
            match = APP_COMMAND_PATTERN.search(text)
            if match is not None:
                is_open = not match.group("verb").lower().startswith("закри")
                self.handle_open_close(text=text, is_open=is_open)
            return

    def handle_paused_command(self, text: str) -> None:
        lowered = text.strip().lower()
        if any(keyword in lowered for keyword in ["продовж", "продовжуй", "продовжи", "віднови"]):
            self.resume_assistant()
        elif any(keyword in lowered for keyword in ["зупини", "стоп", "вимкни", "вимкнись"]):
            self.stop_assistant()

    def report_recognized_command(self, text: str) -> None:
        if not self.paused:
            self.stdout.write(f"Ви сказали: {text}")

    def process_recognized_command(self, text: str) -> None:
        if VOICE_ACTIVE.is_set():
            interrupt_voice()
        self.unrecognized_audio_prompted = False
        self.report_recognized_command(text)

        if self.paused:
            self.handle_paused_command(text)
            return

        self.doing_task(text=text)

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
        pending_file = getattr(self, "pending_file", None)
        self.pending_file = None

        if pending_app is None and pending_file is None:
            return

        if pending_file is not None:
            voicing_and_printing_answer("Добре, скасувала відкриття.")
        elif pending_app is not None:
            action = "відкриття" if pending_app["is_open"] else "закриття"
            voicing_and_printing_answer(
                f"Добре, скасувала {action} програми {pending_app.get('name', '')}."
            )

    def handle_unrecognized_audio(self) -> None:
        pending_file = getattr(self, "pending_file", None)
        if not (self.pending_app or pending_file):
            return
        if (
            pending_file
            and (
                pending_file.get("awaiting_explorer_folder_name")
                or pending_file.get("awaiting_explorer_close_selection")
            )
        ):
            return
        if getattr(self, "unrecognized_audio_prompted", False):
            return

        self.unrecognized_audio_prompted = True
        self.stdout.write(
            "Не розібрав звук. Повторіть відповідь або скажіть «скасувати»."
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
        command_match = APP_COMMAND_PATTERN.match(corrected_name)
        if command_match is not None:
            corrected_name = corrected_name[command_match.end():].strip()
        corrected_name = GENERIC_APP_PREFIX.sub("", corrected_name).strip()
        if not corrected_name:
            action = "відкрити" if pending_app["is_open"] else "закрити"
            voicing_and_printing_answer(
                f"Яку програму {action}? Назвіть її назву."
            )
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
            self.close_app(app_name=pending_app["path"])

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

    def handle_file_open(
        self,
        kind: str,
        target: str,
        new_window: bool = False,
        current_folder: bool = False,
    ) -> None:
        if not target.strip():
            self.pending_file = {
                "kind": kind,
                "awaiting_target": True,
                "new_window": new_window,
                "current_folder": current_folder,
            }
            label = "файл" if kind == "file" else "папку"
            voicing_and_printing_answer(f"Який {label} відкрити? Назвіть його.")
            return

        folder = None
        if current_folder:
            try:
                folder = get_active_explorer_path()
                if folder is None or not os.path.isdir(folder):
                    voicing_and_printing_answer(
                        "Відкрийте потрібну папку у Провіднику й повторіть команду."
                    )
                    return
                targets = find_file_targets_in_folder(target, folder)
            except (OSError, RuntimeError, NotImplementedError) as error:
                self.stdout.write(
                    self.style.WARNING(f"Помилка читання поточної папки: {error}")
                )
                voicing_and_printing_answer(
                    "Не вдалося визначити поточну папку Провідника."
                )
                return
        else:
            targets = find_file_targets(target, expected_kind=kind)
        if not targets:
            suggestions = (
                find_similar_file_targets(target, roots=[folder], expected_kind=kind)
                if current_folder
                else find_similar_file_targets(target, expected_kind=kind)
            )
            if suggestions:
                self.pending_file = {
                    "awaiting_selection": True,
                    "targets": suggestions,
                    "new_window": new_window,
                }
                self.prompt_file_selection(suggestions, prefix="Не знайшла точний збіг.")
                return

            label = "файл" if kind == "file" else "папку"
            if current_folder:
                voicing_and_printing_answer(
                    f"Не знайшла {label} «{target}» у поточній папці. "
                    "Назвіть інший файл або скажіть повний шлях."
                )
            else:
                voicing_and_printing_answer(
                    f"Не знайшла {label} «{target}» у стандартних папках. "
                    "Скажіть повний шлях або назвіть інший елемент."
                )
            return

        if len(targets) > 1:
            self.pending_file = {
                "awaiting_selection": True,
                "targets": targets,
                "new_window": new_window,
            }
            self.prompt_file_selection(targets, prefix="Знайшла кілька точних збігів.")
            return

        self.open_file_target(targets[0], new_window=new_window)

    def prompt_file_selection(self, targets: list[str], prefix: str) -> None:
        choices = "; ".join(
            f"{index}. {os.path.basename(path)} у {os.path.basename(os.path.dirname(path))}"
            for index, path in enumerate(targets, start=1)
        )
        self.stdout.write(f"Варіанти файлів і папок: {choices}")
        voicing_and_printing_answer(
            f"{prefix} Список варіантів виведено на екран. "
            "Назвіть номер потрібного або скажіть «скасувати»."
        )

    def handle_file_selection(self, text: str) -> None:
        pending_file = getattr(self, "pending_file", None)
        if pending_file is None:
            return

        targets = pending_file["targets"]
        selected_index = self.find_selection_index(text, len(targets))
        if selected_index is None:
            voicing_and_printing_answer(
                "Не розпізнала вибір. Назвіть номер потрібного варіанта або скасуйте дію."
            )
            return

        selected_target = targets[selected_index]
        pending_file["awaiting_selection"] = False
        pending_file["awaiting_selection_confirmation"] = True
        pending_file["selected_target"] = selected_target
        voicing_and_printing_answer(
            f"Ви обрали {os.path.basename(selected_target)}. "
            "Відкрити? Скажіть «так» або «ні»."
        )

    def handle_file_selection_confirmation(self, text: str) -> None:
        pending_file = self.pending_file
        if pending_file is None:
            return

        question = "Користувач підтверджує відкриття вибраного файла чи папки."
        analysis = self.analyze_response(text, question=question)
        if analysis.category == ResponseCategory.UNKNOWN:
            voicing_and_printing_answer(
                "Не зрозуміла відповідь. Відкрити вибраний варіант? Скажіть «так» або «ні»."
            )
            return
        if analysis.category == ResponseCategory.REJECTION:
            pending_file["awaiting_selection"] = True
            pending_file["awaiting_selection_confirmation"] = False
            pending_file.pop("selected_target", None)
            self.prompt_file_selection(
                pending_file["targets"],
                prefix="Добре, оберіть інший варіант.",
            )
            return
        if analysis.category != ResponseCategory.CONFIRMATION:
            return

        selected_target = pending_file["selected_target"]
        new_window = pending_file.get("new_window", False)
        self.pending_file = None
        self.open_file_target(selected_target, new_window=new_window)

    @staticmethod
    def find_selection_index(text: str, option_count: int) -> int | None:
        spoken_numbers = {
            int(number)
            for number in re.findall(r"(?<!\w)\d+(?!\w)", text)
        }
        normalized_words = re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)?", text.casefold())
        spoken_numbers.update(
            SELECTION_WORD_TO_NUMBER[word.replace("’", "'")]
            for word in normalized_words
            if word.replace("’", "'") in SELECTION_WORD_TO_NUMBER
        )

        valid_indices = {
            number - 1
            for number in spoken_numbers
            if 1 <= number <= option_count
        }
        if len(valid_indices) != 1:
            return None
        return valid_indices.pop()

    def open_file_target(self, path: str, new_window: bool = False) -> None:
        label = (
            "Провідник"
            if path == "explorer"
            else "Налаштування Windows"
            if path == "ms-settings:"
            else os.path.basename(path) or path
        )
        try:
            if new_window:
                open_target(path, new_window=True)
            else:
                open_target(path)
        except (OSError, RuntimeError) as error:
            self.stdout.write(self.style.WARNING(f"Помилка відкриття: {error}"))
            voicing_and_printing_answer(f"Не вдалося відкрити {label}.")
            return
        voicing_and_printing_answer(f"Відкриваю {label}.")

    def close_explorer(self) -> None:
        try:
            closed_windows = close_explorer_windows()
        except (OSError, RuntimeError, NotImplementedError) as error:
            self.stdout.write(self.style.WARNING(f"Помилка закриття Провідника: {error}"))
            voicing_and_printing_answer("Не вдалося закрити вікна Провідника.")
            return

        if closed_windows:
            voicing_and_printing_answer(
                f"Закрила вікна Провідника. Закрито вікон: {closed_windows}."
            )
        else:
            voicing_and_printing_answer("Відкритих вікон Провідника не знайшла.")

    def close_explorer_folder(self, folder_name: str) -> None:
        folder_name = folder_name.strip().strip("\"'«».,!? ")
        if not folder_name:
            voicing_and_printing_answer("Назвіть папку, яку потрібно закрити.")
            return

        try:
            matching_tabs = find_open_explorer_folders(folder_name)
        except (OSError, RuntimeError, NotImplementedError) as error:
            self.stdout.write(self.style.WARNING(f"Помилка закриття папки: {error}"))
            voicing_and_printing_answer("Не вдалося закрити вікно цієї папки.")
            return

        if not matching_tabs:
            voicing_and_printing_answer(
                f"Не знайшла відкритого вікна папки {folder_name}."
            )
            return

        if len(matching_tabs) > 1:
            self.pending_file = {
                "awaiting_explorer_close_selection": True,
                "targets": matching_tabs,
            }
            choices = "; ".join(
                f"{index}. {tab.name} у {tab.path}, вкладка {tab.tab_index + 1}"
                for index, tab in enumerate(matching_tabs, start=1)
            )
            self.stdout.write(f"Відкриті папки: {choices}")
            voicing_and_printing_answer(
                "Знайшла кілька відкритих папок. "
                "Назвіть номер тієї, яку потрібно закрити, або скажіть «скасувати»."
            )
            return

        self._close_selected_explorer_folder(matching_tabs[0])

    def handle_explorer_close_selection(self, text: str) -> None:
        pending_file = self.pending_file
        if pending_file is None:
            return

        targets = pending_file["targets"]
        selected_index = self.find_selection_index(text, len(targets))
        if selected_index is None:
            return

        self.pending_file = None
        self._close_selected_explorer_folder(targets[selected_index])

    def _close_selected_explorer_folder(self, tab) -> None:
        try:
            closed = close_explorer_tab(tab)
        except (OSError, RuntimeError, NotImplementedError) as error:
            self.stdout.write(self.style.WARNING(f"Помилка закриття папки: {error}"))
            voicing_and_printing_answer("Не вдалося закрити цю вкладку Провідника.")
            return

        if closed:
            voicing_and_printing_answer(f"Закрила папку {tab.name}.")
        else:
            voicing_and_printing_answer(
                "Не знайшла вибрану вкладку Провідника. Повторіть команду."
            )

    def navigate_explorer_back(self) -> None:
        try:
            navigated = navigate_explorer_back()
        except (OSError, RuntimeError, NotImplementedError) as error:
            self.stdout.write(self.style.WARNING(f"Помилка переходу назад: {error}"))
            voicing_and_printing_answer("Не вдалося перейти назад у Провіднику.")
            return

        if navigated:
            voicing_and_printing_answer(
                "Надіслала Провіднику команду перейти до попередньої папки."
            )
        else:
            voicing_and_printing_answer("Не знайшла активного вікна Провідника.")

    def navigate_explorer_forward(self, requested_name: str = "") -> None:
        try:
            folders = get_active_explorer_subfolders()
        except (OSError, RuntimeError, NotImplementedError) as error:
            self.stdout.write(self.style.WARNING(f"Помилка читання папок: {error}"))
            voicing_and_printing_answer("Не вдалося прочитати папки у Провіднику.")
            return

        if folders is None:
            voicing_and_printing_answer("Не знайшла активного вікна Провідника.")
            return
        if not folders:
            voicing_and_printing_answer("У цій папці немає вкладених папок.")
            return

        if requested_name:
            self.pending_file = {
                "awaiting_explorer_folder_name": True,
                "targets": folders,
            }
            self.handle_explorer_folder_name(requested_name)
            if self.pending_file is None:
                return

        if len(folders) > 7:
            if requested_name:
                voicing_and_printing_answer(
                    f"Не знайшла папку «{requested_name}». "
                    "У цій папці більше семи підпапок. Повторіть точну назву."
                )
            else:
                voicing_and_printing_answer(
                    "У цій папці більше семи підпапок. Назвіть конкретну папку."
                )
        else:
            names = "; ".join(
                f"{index}. {self._explorer_folder_name(path)}"
                for index, path in enumerate(folders, start=1)
            )
            self.stdout.write(f"Підпапки: {names}")
            if requested_name:
                voicing_and_printing_answer(
                    f"Не знайшла папку «{requested_name}». "
                    "Список показано на екрані. Назвіть номер потрібної папки "
                    "або повторіть її назву."
                )
            else:
                voicing_and_printing_answer(
                    "Підпапки виведено на екран. Назвіть назву папки "
                    "або її номер у списку."
                )

        self.pending_file = {
            "awaiting_explorer_folder_name": True,
            "targets": folders,
        }

    def handle_explorer_folder_name(self, text: str) -> None:
        pending_file = self.pending_file
        if pending_file is None:
            return

        targets = pending_file["targets"]
        selected_index = self.find_selection_index(text, len(targets))
        match = (
            targets[selected_index]
            if selected_index is not None
            else self._match_explorer_folder_name(text, targets)
        )
        if match is None:
            return

        self.pending_file = None
        try:
            navigated = navigate_explorer_to(match)
        except (OSError, RuntimeError, NotImplementedError) as error:
            self.stdout.write(
                self.style.WARNING(f"Помилка переходу до папки: {error}")
            )
            voicing_and_printing_answer(
                "Не вдалося перейти до цієї папки у поточному вікні."
            )
            return

        if navigated:
            voicing_and_printing_answer(
                "Перейшла до папки "
                f"{self._explorer_folder_name(match)} у поточному вікні."
            )
        else:
            voicing_and_printing_answer("Не знайшла активного вікна Провідника.")

    @staticmethod
    def _explorer_folder_name(path: str) -> str:
        trimmed_path = path.rstrip("\\/")
        drive, _tail = os.path.splitdrive(path)
        return os.path.basename(trimmed_path) or drive or path

    @classmethod
    def _match_explorer_folder_name(
        cls,
        spoken_text: str,
        targets: list[str],
    ) -> str | None:
        normalized_words = re.findall(r"[^\W_]+", spoken_text.casefold())
        words = [word for word in normalized_words if len(word) >= 3]
        if not words:
            return None

        ranked: list[tuple[float, str]] = []
        for path in targets:
            folder_words = re.findall(
                r"[^\W_]+",
                cls._explorer_folder_name(path).casefold(),
            )
            scores = [
                similarity(word, folder_word)
                for word in words
                for folder_word in folder_words
                if len(folder_word) >= 3
            ]
            transliterated_words = [
                transliterate(word)
                for word in words
                if re.search(r"[а-яіїєґ]", word)
            ]
            scores.extend(
                similarity(word, folder_word)
                for word in transliterated_words
                for folder_word in folder_words
                if len(folder_word) >= 3
            )
            if scores:
                ranked.append((max(scores), path))

        ranked.sort(key=lambda item: (-item[0], item[1].casefold()))
        if not ranked or ranked[0][0] < 0.8:
            return None
        if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
            return None
        return ranked[0][1]

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
        selected_index = self.find_selection_index(text, len(suggestions))

        if selected_index is not None:
            name, path = suggestions[selected_index]
        else:
            name_query = re.sub(r"\b(?:варіант|номер|пункт)\b|\d+", " ", text, flags=re.IGNORECASE)
            exact_match = find_exact_match(
                name_query,
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

        if selected_index is None:
            is_open = pending_app["is_open"]
            self.pending_app = None
            voicing_and_printing_answer(f"Вибрано програму {name}.")
            self.execute_app_action(name, path, is_open)
            return

        pending_app["awaiting_selection"] = False
        pending_app["awaiting_selection_confirmation"] = True
        pending_app["selected_name"] = name
        pending_app["selected_path"] = path
        voicing_and_printing_answer(
            f"Ви обрали {name}. Виконати дію? Скажіть «так» або «ні»."
        )

    def handle_app_selection_confirmation(self, text: str) -> None:
        pending_app = self.pending_app
        if pending_app is None:
            return

        question = f"Підтвердження вибору програми {pending_app['selected_name']}."
        analysis = self.analyze_response(text, question=question)
        if analysis.category == ResponseCategory.UNKNOWN:
            voicing_and_printing_answer(
                f"Не зрозуміла відповідь. Виконати дію з програмою "
                f"{pending_app['selected_name']}? Скажіть «так» або «ні»."
            )
            return
        if analysis.category == ResponseCategory.REJECTION:
            pending_app["awaiting_selection"] = True
            pending_app["awaiting_selection_confirmation"] = False
            pending_app.pop("selected_name", None)
            pending_app.pop("selected_path", None)
            options = "; ".join(
                f"{index}. {name}"
                for index, (name, _path) in enumerate(pending_app["suggestions"], start=1)
            )
            self.stdout.write(f"Схожі програми: {options}")
            voicing_and_printing_answer(
                "Добре, оберіть інший варіант за номером або назвою."
            )
            return
        if analysis.category != ResponseCategory.CONFIRMATION:
            return

        name = pending_app["selected_name"]
        path = pending_app["selected_path"]
        is_open = pending_app["is_open"]
        self.pending_app = None
        self.execute_app_action(name, path, is_open)

    def execute_app_action(self, name: str, path: str, is_open: bool) -> None:
        command = register_found_app(name=name, path=path)
        if is_open:
            voicing_and_printing_answer(f"Відкриваю {name}")
            if self.open_app(path=path):
                increment_open_count(command)
        else:
            voicing_and_printing_answer(f"Закриваю {name}")
            self.close_app(app_name=path)

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

            if system == "Windows" and app_name.casefold().endswith(".lnk"):
                result = subprocess.run(
                    args=[
                        "powershell",
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        (
                            "$shell = New-Object -ComObject WScript.Shell; "
                            "$shortcut = $shell.CreateShortcut("
                            "$env:ASSISTANT_SHORTCUT_PATH); "
                            "if (-not $shortcut.TargetPath) { "
                            "throw 'Ярлик не має цільового файла' }; "
                            "Write-Output $shortcut.TargetPath"
                        ),
                    ],
                    env={**os.environ, "ASSISTANT_SHORTCUT_PATH": app_name},
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                if result.returncode != 0 or not result.stdout.strip():
                    message = result.stderr.strip() or "Не вдалося прочитати ціль ярлика"
                    self.stdout.write(
                        self.style.WARNING(f"Не вдалося визначити процес програми: {message}")
                    )
                    return
                app_name = result.stdout.strip()

            app_name = os.path.basename(app_name)
            if system == "Windows" and not app_name.lower().endswith(".exe"):
                app_name += ".exe"
            if system == "Windows":
                result = subprocess.run(
                    args=["taskkill", "/IM", app_name, "/F"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            else:
                result = subprocess.run(
                    args=["pkill", "-f", app_name],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            if result.returncode != 0:
                message = result.stderr.strip() or result.stdout.strip()
                if not message:
                    message = f"Процес {app_name} не знайдено або його не вдалося завершити."
                self.stdout.write(
                    self.style.WARNING(f"Не вдалося закрити програму: {message}")
                )
        except Exception as error:
            self.stdout.write(self.style.WARNING(f"Помилка закриття: {error}"))
