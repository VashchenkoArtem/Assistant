from unittest.mock import Mock, patch
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Assistant.settings")

import django

django.setup()

from core.management.commands import run_assistant
from core.management.commands.run_assistant import Command
from core.response_analysis import (
    ResponseAnalysis,
    ResponseCategory,
    ResponseLearner,
    ResponseRepository,
    ResponseSource,
)


class QueuedAnalyzer:
    def __init__(self, results):
        self.results = iter(results)

    def analyze(self, question, answer, dialog_context):
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
    command.response_analyzer = QueuedAnalyzer(results)
    command.open_app = Mock()
    command.close_app = Mock()
    return command


def test_unknown_app_confirmation_reprompts_without_executing(tmp_path):
    command = make_command(
        tmp_path,
        [ResponseAnalysis(ResponseCategory.UNKNOWN, 0.4)],
    )

    with (
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
        patch.object(run_assistant, "register_found_app") as register,
    ):
        command.handle_confirmation("можливо")

    assert command.pending_app is not None
    command.open_app.assert_not_called()
    register.assert_not_called()
    assert "так або ні" in speak.call_args.args[0]


def test_semantic_candidate_requires_learning_confirmation_before_action(tmp_path):
    command = make_command(
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
        command.open_app.assert_not_called()
        register.assert_not_called()
        assert "Запам'ятати фразу" in speak.call_args.args[0]

        command.handle_learning_confirmation("так")

    assert command.response_repository.exists("без питань, вперед")
    assert command.pending_learning_candidate is None
    assert command.pending_app is None
    command.open_app.assert_called_once_with("C:\\Apps\\example.exe")
    register.assert_called_once()


def test_unknown_learning_answer_reprompts_and_keeps_candidate_pending(tmp_path):
    command = make_command(
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
    command.open_app.assert_not_called()
    register.assert_not_called()
    assert "Не впевнена" in speak.call_args.args[0]
    assert "Запам'ятати фразу" in speak.call_args.args[0]


def test_rejecting_learning_does_not_cancel_pending_app_action(tmp_path):
    command = make_command(
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
    command.open_app.assert_called_once_with("C:\\Apps\\example.exe")
    register.assert_called_once()
