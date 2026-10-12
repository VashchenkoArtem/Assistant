import os
from collections.abc import Iterable
from unittest.mock import Mock, patch
import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Assistant.settings")

import django

django.setup()

from core.management.commands import run_assistant
from core.management.commands.run_assistant import Command
from core.response_analysis import (
    ResponseAnalysis,
    DialogContext,
    ResponseCategory,
    ResponseAnalyzer,
    ResponseLearner,
    ResponseRepository,
    ResponseSource,
)
from utils import voicing_answer


class QueuedAnalyzer(ResponseAnalyzer):
    def __init__(self, repository: ResponseRepository, results: Iterable[ResponseAnalysis]):
        super().__init__(repository)
        self.results = iter(results)

    def analyze(self, question: str, answer: str, dialog_context: DialogContext | None = None) -> ResponseAnalysis:
        _ = question, answer, dialog_context
        return next(self.results)


def make_command(tmp_path, results):
    command = Command()
    command.pending_app = {
        "name": "Example App",
        "path": "C:\\Apps\\example.exe",
        "is_open": True,
    }
    command.pending_learning_candidate = None
    command.response_repository = ResponseRepository(
        f"sqlite:///{tmp_path / 'responses.db'}"
    )
    command.response_learner = ResponseLearner(command.response_repository)
    command.response_analyzer = QueuedAnalyzer(command.response_repository, results)
    open_app = Mock()
    command.open_app = open_app
    command.close_app = Mock()
    return command, open_app


def test_listener_does_not_record_while_assistant_is_speaking():
    recognizer = Mock()
    voicing_answer.VOICE_ACTIVE.set()
    try:
        audio = Command.listen_for_audio(recognizer, source=object())
    finally:
        voicing_answer.VOICE_ACTIVE.clear()

    assert audio is None
    recognizer.listen.assert_not_called()


def test_synchronous_voice_playback_marks_audio_as_busy():
    def verify_voice_state(text):
        assert text == "Говорю"
        assert voicing_answer.VOICE_ACTIVE.is_set()
        assert voicing_answer.AUDIO_LOCK.locked()

    with patch.object(voicing_answer, "voicing_text", side_effect=verify_voice_state):
        voicing_answer.run_voice("Говорю", wait=True)

    assert not voicing_answer.VOICE_ACTIVE.is_set()


def test_app_list_prompt_is_spoken_once(tmp_path):
    command, _ = make_command(tmp_path, [])
    command.pending_app = None

    with (
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
        patch.object(run_assistant, "get_list_installed_apps", return_value={"Steam": "steam.exe"}),
    ):
        command.doing_task("додатки")

    prompts = [
        call.args[0]
        for call in speak.call_args_list
        if call.args and call.args[0] == "Відкриваю список додатків..."
    ]
    assert prompts == ["Відкриваю список додатків..."]


def test_app_name_confirmation_prompt_is_spoken_once(tmp_path):
    command, _ = make_command(tmp_path, [])
    command.pending_app = None

    with (
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
        patch.object(run_assistant, "get_known_apps", return_value={"Steam": "C:\\Apps\\steam.exe"}),
        patch.object(run_assistant, "is_unknown", return_value=True),
    ):
        command.handle_open_close("відкрий Steam", is_open=True)

    confirmation_prompts = [
        call.args[0]
        for call in speak.call_args_list
        if call.args and call.args[0].startswith("Чи правильно я почув назву?")
    ]
    assert confirmation_prompts == [
        "Чи правильно я почув назву? Назва програми: Steam?"
    ]


def test_pause_command_is_available_while_waiting_for_app_confirmation(tmp_path):
    command, _ = make_command(tmp_path, [])
    command.paused = False

    with patch.object(run_assistant, "run_voice"):
        command.doing_task("пауза")

    assert command.paused is True
    assert command.pending_app is not None


def test_stop_command_clears_pending_dialog_state(tmp_path):
    command, _ = make_command(tmp_path, [])
    command.pending_learning_candidate = command.response_learner.create_candidate(
        "ще одна згода",
        ResponseCategory.CONFIRMATION,
        0.9,
    )

    with patch.object(run_assistant, "run_voice"):
        command.doing_task("зупини асистента")

    assert command.run is False
    assert command.pending_app is None
    assert command.pending_learning_candidate is None


def test_unknown_app_confirmation_reprompts_without_executing(tmp_path):
    command, open_app = make_command(
        tmp_path,
        [ResponseAnalysis(ResponseCategory.UNKNOWN, 0.4)],
    )

    with (
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
        patch.object(run_assistant, "register_found_app") as register,
    ):
        command.handle_confirmation("не впевнений але думаю що правильно")

    assert command.pending_app is not None
    open_app.assert_not_called()
    register.assert_not_called()
    assert "так або ні" in speak.call_args.args[0]


def test_user_can_cancel_pending_app_after_confirmation_reprompt(tmp_path):
    command, open_app = make_command(
        tmp_path,
        [ResponseAnalysis(ResponseCategory.UNKNOWN, 0.4)],
    )

    with (
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
        patch.object(run_assistant, "register_found_app") as register,
    ):
        command.doing_task("не впевнений")
        assert command.pending_app is not None

        command.doing_task("скасувати дію")

    assert command.pending_app is None
    assert command.pending_learning_candidate is None
    open_app.assert_not_called()
    register.assert_not_called()
    assert "скасувала відкриття" in speak.call_args.args[0]


def test_user_can_cancel_while_assistant_awaits_corrected_app_name(tmp_path):
    command, open_app = make_command(tmp_path, [])
    command.pending_app = {
        "name": "Example App",
        "path": "C:\\Apps\\example.exe",
        "is_open": True,
        "awaiting_name": True,
    }

    with (
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
        patch.object(run_assistant, "register_found_app") as register,
    ):
        command.doing_task("відміна")

    assert command.pending_app is None
    open_app.assert_not_called()
    register.assert_not_called()
    assert "скасувала відкриття" in speak.call_args.args[0]


def test_user_can_cancel_action_while_confirming_phrase_learning(tmp_path):
    command, open_app = make_command(tmp_path, [])
    command.pending_learning_candidate = command.response_learner.create_candidate(
        "звісно відкривай",
        ResponseCategory.CONFIRMATION,
        0.9,
    )

    with (
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
        patch.object(run_assistant, "register_found_app") as register,
    ):
        command.doing_task("скасуй")

    assert command.pending_learning_candidate is None
    assert command.pending_app is None
    assert not command.response_repository.exists("звісно відкривай")
    open_app.assert_not_called()
    register.assert_not_called()
    assert "скасувала відкриття" in speak.call_args.args[0]


def test_rejecting_guessed_app_name_keeps_action_and_accepts_corrected_name(tmp_path):
    command, open_app = make_command(
        tmp_path,
        [ResponseAnalysis(ResponseCategory.REJECTION, 1.0)],
    )

    with (
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
        patch.object(run_assistant, "register_found_app") as register,
    ):
        command.handle_confirmation("ні")

        assert command.pending_app is not None
        assert command.pending_app["awaiting_name"] is True
        open_app.assert_not_called()
        assert "точну назву" in speak.call_args.args[0]

        with (
            patch.object(
                run_assistant,
                "get_known_apps",
                return_value={"Sticky Notes": "C:\\Apps\\Sticky Notes.exe"},
            ),
            patch.object(run_assistant, "is_unknown", return_value=False),
        ):
            command.doing_task("Sticky Notes")

    open_app.assert_called_once_with(path="C:\\Apps\\Sticky Notes.exe")
    register.assert_called_once_with(
        name="Sticky Notes",
        path="C:\\Apps\\Sticky Notes.exe",
    )
    assert command.pending_app is None


@pytest.mark.parametrize(
    ("spoken_verb", "is_open"),
    [
        ("відкрий", True),
        ("відкрити", True),
        ("відкривай", True),
        ("відкривати", True),
        ("закрий", False),
        ("закрити", False),
        ("закривай", False),
        ("закривати", False),
    ],
)
def test_app_command_accepts_verb_forms(tmp_path, spoken_verb, is_open):
    command, open_app = make_command(tmp_path, [])
    command.pending_app = None
    command.pending_learning_candidate = None

    with (
        patch.object(command, "close_app") as close_app,
        patch.object(
            run_assistant,
            "get_known_apps",
            return_value={"Steam": "C:\\Apps\\steam.exe"},
        ),
        patch.object(run_assistant, "is_unknown", return_value=False),
        patch.object(run_assistant, "register_found_app"),
        patch.object(run_assistant, "voicing_and_printing_answer"),
    ):
        command.doing_task(f"{spoken_verb} програму Steam")

    if is_open:
        open_app.assert_called_once_with(path="C:\\Apps\\steam.exe")
    else:
        close_app.assert_called_once_with(app_name="steam.exe")


def test_missing_app_name_prompts_and_accepts_follow_up_title(tmp_path):
    command, open_app = make_command(tmp_path, [])
    command.pending_app = None
    command.pending_learning_candidate = None

    with (
        patch.object(
            run_assistant,
            "get_known_apps",
            return_value={"Sticky Notes": "C:\\Apps\\Sticky Notes.exe"},
        ),
        patch.object(run_assistant, "is_unknown", return_value=False),
        patch.object(run_assistant, "register_found_app"),
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
    ):
        command.doing_task("Відкрий програму")

        assert command.pending_app == {
            "is_open": True,
            "awaiting_name": True,
        }
        assert "Яку програму відкрити" in speak.call_args.args[0]

        command.doing_task("Sticky Notes")

    open_app.assert_called_once_with(path="C:\\Apps\\Sticky Notes.exe")
    assert command.pending_app is None


def test_windows_store_app_uses_apps_folder_launcher(tmp_path):
    command, _ = make_command(tmp_path, [])
    store_path = "appx://SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"

    with (
        patch.object(run_assistant.platform, "system", return_value="Windows"),
        patch.object(run_assistant.os, "startfile") as startfile,
    ):
        Command.open_app(command, store_path)

    startfile.assert_called_once_with(
        "shell:AppsFolder\\SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"
    )


def test_windows_store_app_close_stops_processes_from_package(tmp_path):
    command, _ = make_command(tmp_path, [])
    store_path = "appx://SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"

    with (
        patch.object(run_assistant.platform, "system", return_value="Windows"),
        patch.object(run_assistant.subprocess, "run") as run,
    ):
        Command.close_app(command, store_path)

    run.assert_called_once()
    assert run.call_args.kwargs["args"][:3] == [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
    ]
    assert run.call_args.kwargs["env"]["ASSISTANT_PACKAGE_FAMILY"] == (
        "SpotifyAB.SpotifyMusic_zpdnekdrzrea0"
    )
    assert "Get-CimInstance Win32_Process" in run.call_args.kwargs["args"][-1]


def test_semantic_candidate_requires_learning_confirmation_before_action(tmp_path):
    command, open_app = make_command(
        tmp_path,
        [
            ResponseAnalysis(
                ResponseCategory.CONFIRMATION,
                0.91,
                matched_pattern="звичайно",
                source=ResponseSource.SEMANTIC,
            ),
            ResponseAnalysis(
                ResponseCategory.CONFIRMATION,
                1.0,
                matched_pattern="так",
                source=ResponseSource.PATTERN,
            ),
        ],
    )

    with (
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
        patch.object(run_assistant, "register_found_app") as register,
    ):
        command.handle_confirmation("без питань, вперед")

        assert command.pending_learning_candidate is not None
        assert command.pending_learning_candidate.text == "без питань, вперед"
        assert command.pending_app is not None
        open_app.assert_not_called()
        register.assert_not_called()
        assert "Запам'ятати фразу" in speak.call_args.args[0]

        command.handle_learning_confirmation("так")

    assert command.response_repository.exists("без питань, вперед")
    assert command.pending_learning_candidate is None
    assert command.pending_app is None
    open_app.assert_called_once_with("C:\\Apps\\example.exe")
    register.assert_called_once()


def test_builtin_permission_confirmation_is_not_offered_for_learning(tmp_path):
    command, open_app = make_command(tmp_path, [])
    command.response_analyzer = ResponseAnalyzer(command.response_repository)

    with (
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
        patch.object(run_assistant, "register_found_app") as register,
    ):
        command.handle_confirmation("можеш відкривати")

    assert command.pending_learning_candidate is None
    assert command.pending_app is None
    open_app.assert_called_once_with("C:\\Apps\\example.exe")
    register.assert_called_once()
    assert all(
        "Запам'ятати фразу" not in call.args[0]
        for call in speak.call_args_list
    )


def test_unknown_learning_answer_reprompts_and_keeps_candidate_pending(tmp_path):
    command, open_app = make_command(
        tmp_path,
        [
            ResponseAnalysis(
                ResponseCategory.CONFIRMATION,
                0.91,
                matched_pattern="звичайно",
                source=ResponseSource.SEMANTIC,
            ),
            ResponseAnalysis(ResponseCategory.UNKNOWN, 0.3),
        ],
    )

    with (
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
        patch.object(run_assistant, "register_found_app") as register,
    ):
        command.handle_confirmation("без питань, вперед")
        pending_candidate = command.pending_learning_candidate

        command.handle_learning_confirmation("важко сказати")

    assert command.pending_learning_candidate is pending_candidate
    assert command.pending_app is not None
    open_app.assert_not_called()
    register.assert_not_called()
    assert "Не впевнена" in speak.call_args.args[0]
    assert "Запам'ятати фразу" in speak.call_args.args[0]


def test_rejecting_learning_does_not_cancel_pending_app_action(tmp_path):
    command, open_app = make_command(
        tmp_path,
        [
            ResponseAnalysis(
                ResponseCategory.CONFIRMATION,
                0.91,
                matched_pattern="звичайно",
                source=ResponseSource.SEMANTIC,
            ),
            ResponseAnalysis(
                ResponseCategory.REJECTION,
                1.0,
                matched_pattern="ні",
                source=ResponseSource.PATTERN,
            ),
        ],
    )

    with (
        patch.object(run_assistant, "voicing_and_printing_answer"),
        patch.object(run_assistant, "register_found_app") as register,
    ):
        command.handle_confirmation("без питань, вперед")
        command.handle_learning_confirmation("ні")

    assert not command.response_repository.exists("без питань, вперед")
    assert command.pending_learning_candidate is None
    assert command.pending_app is None
    open_app.assert_called_once_with("C:\\Apps\\example.exe")
    register.assert_called_once()
