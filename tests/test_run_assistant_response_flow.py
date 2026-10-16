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


@pytest.fixture(autouse=True)
def increment(request):
    # Flow tests mock register_found_app, so they must not touch the real DB.
    with patch.object(run_assistant, "increment_open_count") as mocked:
        yield mocked


@pytest.fixture(autouse=True)
def app_open_counts():
    with patch.object(run_assistant, "get_app_open_counts", return_value={}):
        yield


def test_recognizer_is_calibrated_and_keeps_short_phrases():
    recognizer = Mock()
    source = object()

    Command.configure_recognizer(recognizer, source)

    recognizer.adjust_for_ambient_noise.assert_called_once_with(source, duration=1)
    assert recognizer.dynamic_energy_threshold is True
    assert recognizer.phrase_threshold == 0.15
    assert recognizer.pause_threshold == 0.8
    assert recognizer.non_speaking_duration == 0.5


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


def _open_known_app(command, spoken="відкрий програму Steam"):
    with (
        patch.object(
            run_assistant,
            "get_known_apps",
            return_value={"Steam": "C:\\Apps\\steam.exe"},
        ),
        patch.object(run_assistant, "is_unknown", return_value=False),
        patch.object(run_assistant, "register_found_app") as register,
        patch.object(run_assistant, "voicing_and_printing_answer"),
    ):
        command.doing_task(spoken)
    return register


def test_opening_known_app_increments_open_count_once(tmp_path, increment):
    command, open_app = make_command(tmp_path, [])
    command.pending_app = None

    register = _open_known_app(command)

    open_app.assert_called_once_with(path="C:\\Apps\\steam.exe")
    increment.assert_called_once_with(register.return_value)


def test_app_search_uses_open_count_only_after_similarity_tie(tmp_path):
    command, open_app = make_command(tmp_path, [])
    command.pending_app = None
    command.pending_learning_candidate = None

    with (
        patch.object(
            run_assistant,
            "get_known_apps",
            return_value={
                "Steam": "C:\\Apps\\steam.exe",
                "steam": "C:\\Apps\\steam-alt.exe",
            },
        ),
        patch.object(
            run_assistant,
            "get_app_open_counts",
            return_value={"Steam": 1, "steam": 8},
        ) as get_open_counts,
        patch.object(run_assistant, "is_unknown", return_value=False),
        patch.object(run_assistant, "register_found_app"),
        patch.object(run_assistant, "voicing_and_printing_answer"),
    ):
        command.doing_task("відкрий steam")

    get_open_counts.assert_called_once()
    open_app.assert_called_once_with(path="C:\\Apps\\steam-alt.exe")


def test_closing_app_does_not_increment_open_count(tmp_path, increment):
    command, _ = make_command(tmp_path, [])
    command.pending_app = None

    _open_known_app(command, spoken="закрий програму Steam")

    increment.assert_not_called()


def test_failed_open_does_not_increment_open_count(tmp_path, increment):
    command, open_app = make_command(tmp_path, [])
    command.pending_app = None
    open_app.return_value = False

    _open_known_app(command)

    open_app.assert_called_once()
    increment.assert_not_called()


def test_confirmed_new_app_increments_open_count(tmp_path, increment):
    command, open_app = make_command(
        tmp_path,
        [ResponseAnalysis(ResponseCategory.CONFIRMATION, 1.0, source=ResponseSource.PATTERN)],
    )

    with (
        patch.object(run_assistant, "voicing_and_printing_answer"),
        patch.object(run_assistant, "register_found_app") as register,
    ):
        command.handle_confirmation("так")

    open_app.assert_called_once_with("C:\\Apps\\example.exe")
    increment.assert_called_once_with(register.return_value)


@pytest.mark.parametrize("answer", ["точно", "вірно", "yes"])
def test_short_confirmation_variants_complete_pending_app_action(tmp_path, answer):
    command, open_app = make_command(tmp_path, [])
    command.response_analyzer = ResponseAnalyzer(command.response_repository)

    with (
        patch.object(run_assistant, "voicing_and_printing_answer"),
        patch.object(run_assistant, "register_found_app"),
    ):
        command.handle_confirmation(answer)

    open_app.assert_called_once_with("C:\\Apps\\example.exe")
    assert command.pending_app is None


@pytest.mark.parametrize("answer", ["нє", "неа", "no"])
def test_short_rejection_variants_reject_pending_app_name(tmp_path, answer):
    command, open_app = make_command(tmp_path, [])
    command.response_analyzer = ResponseAnalyzer(command.response_repository)

    with (
        patch.object(run_assistant, "voicing_and_printing_answer"),
        patch.object(run_assistant, "register_found_app"),
    ):
        command.handle_confirmation(answer)

    open_app.assert_not_called()
    assert command.pending_app is not None
    assert command.pending_app["awaiting_name"] is True


def test_open_app_reports_success_and_failure(tmp_path):
    command, _ = make_command(tmp_path, [])

    with (
        patch.object(run_assistant.platform, "system", return_value="Linux"),
        patch.object(run_assistant.subprocess, "Popen") as popen,
    ):
        assert Command.open_app(command, "/usr/bin/true") is True

        popen.side_effect = OSError("boom")
        assert Command.open_app(command, "/nonexistent") is False
