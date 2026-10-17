import pytest
from django.test import override_settings
from sqlalchemy import select

from core.response_analysis import (
    DecisionEngine,
    DialogContext,
    DialogState,
    PatternMatcher,
    ResponseAnalyzer,
    ResponseCategory,
    ResponseLearner,
    ResponseRepository,
    SemanticAnalyzer,
    TextNormalizer,
)
from core.response_analysis.models import ResponseConfirmation, ResponseRejection


def make_repository(tmp_path):
    db_path = tmp_path / "test_responses.sqlite3"
    return ResponseRepository(f"sqlite:///{db_path}")


def test_repository_default_uses_django_database(tmp_path):
    database_path = tmp_path / "db.sqlite3"
    with override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": database_path,
            }
        }
    ):
        repository = ResponseRepository()

    assert repository.engine.url.database == str(database_path)
    assert len(repository.get_all()) == 46
    repository.engine.dispose()


def test_normalizer_reduces_case_and_spacing():
    assert TextNormalizer.normalize("  ТАК!!! ") == "так"
    assert TextNormalizer.normalize("Добре!!!") == "добре"


def test_pattern_matcher_identifies_known_patterns(tmp_path):
    repository = make_repository(tmp_path)
    matcher = PatternMatcher(repository)

    confirmation = matcher.match("так")
    rejection = matcher.match("не хочу")

    assert confirmation is not None
    assert confirmation.category == ResponseCategory.CONFIRMATION
    assert rejection is not None
    assert rejection.category == ResponseCategory.REJECTION


def test_semantic_analyzer_handles_near_variants(tmp_path):
    repository = make_repository(tmp_path)
    analyzer = SemanticAnalyzer(repository)

    confirmation = analyzer.analyze("ну добре, давай")
    rejection = analyzer.analyze("чому б і ні")

    assert confirmation.category == ResponseCategory.CONFIRMATION
    assert confirmation.confidence >= 0.62
    assert rejection.category == ResponseCategory.UNKNOWN or rejection.category == ResponseCategory.REJECTION


def test_decision_engine_resolves_negation_conflict(tmp_path):
    repository = make_repository(tmp_path)
    engine = DecisionEngine(repository)

    result = engine.decide("так, але не зараз")
    assert result.category == ResponseCategory.REJECTION


def test_decision_engine_recognizes_permission_as_builtin_confirmation(tmp_path):
    repository = make_repository(tmp_path)
    engine = DecisionEngine(repository)

    result = engine.decide("можеш відкривати")

    assert result.category == ResponseCategory.CONFIRMATION
    assert result.source.value == "RULE"


@pytest.mark.parametrize(
    "answer",
    [
        "так",
        "Так!",
        "так,",
        "да",
        "ага",
        "угу",
        "звісно",
        "точно",
        "вірно",
        "yes",
    ],
)
def test_decision_engine_recognizes_common_short_confirmations_from_database(
    tmp_path, answer
):
    engine = DecisionEngine(make_repository(tmp_path))

    result = engine.decide(answer)

    assert result.category == ResponseCategory.CONFIRMATION
    assert result.confidence == 1.0
    assert result.source.value == "PATTERN"


@pytest.mark.parametrize(
    "answer",
    [
        "ні",
        "Ні!",
        "ні,",
        "нє",
        "ніт",
        "неа",
        "нет",
        "no",
    ],
)
def test_decision_engine_recognizes_common_short_rejections_from_database(
    tmp_path, answer
):
    engine = DecisionEngine(make_repository(tmp_path))

    result = engine.decide(answer)

    assert result.category == ResponseCategory.REJECTION
    assert result.confidence == 1.0
    assert result.source.value == "PATTERN"


def test_repository_does_not_seed_single_character_responses(tmp_path):
    repository = make_repository(tmp_path)
    patterns = {pattern.pattern for pattern in repository.get_all()}

    assert "д" not in patterns
    assert "н" not in patterns


def test_repository_adds_missing_defaults_to_existing_database(tmp_path):
    repository = make_repository(tmp_path)
    repository.delete(repository.find_by_pattern("звісно").id)
    repository.seed_default_patterns()

    assert repository.find_by_pattern("звісно") is not None
    assert len(repository.get_all()) == 46


def test_decision_engine_matches_short_words_at_word_boundaries(tmp_path):
    engine = DecisionEngine(make_repository(tmp_path))

    assert not engine._contains_negation("нічого")
    assert not engine._contains_confirmation("підтакувати")
    assert engine.decide("неможна").category == ResponseCategory.REJECTION


def test_decision_engine_keeps_uncertain_answer_unknown(tmp_path):
    repository = make_repository(tmp_path)
    engine = DecisionEngine(repository)

    result = engine.decide("не впевнений, але думаю, що правильно")

    assert result.category == ResponseCategory.UNKNOWN


def test_response_analyzer_returns_confirmation_for_positive_answer(tmp_path):
    repository = make_repository(tmp_path)
    analyzer = ResponseAnalyzer(repository)
    context = DialogContext(state=DialogState.WAITING_FOR_RESPONSE, pending_action="ADD_PROGRAM")

    result = analyzer.analyze("Ви хочете додати програму?", "ну добре, давай", context)
    assert result.category == ResponseCategory.CONFIRMATION
    assert result.confidence >= 0.62


def test_learning_system_accepts_short_candidate(tmp_path):
    repository = make_repository(tmp_path)
    learner = ResponseLearner(repository)

    candidate = learner.create_candidate("чому б і ні", ResponseCategory.CONFIRMATION, 0.88)
    assert candidate is not None
    assert candidate.category == ResponseCategory.CONFIRMATION

    saved = learner.accept_candidate(candidate)
    assert saved.pattern == "чому б і ні"


def test_learning_rejects_long_sentence_candidate(tmp_path):
    repository = make_repository(tmp_path)
    learner = ResponseLearner(repository)

    candidate = learner.create_candidate(
        "Ну я взагалі не знаю але якщо тобі потрібно то можеш це зробити",
        ResponseCategory.CONFIRMATION,
        0.9,
    )
    assert candidate is None


def test_confirmation_and_rejection_decisions_use_separate_tables(tmp_path):
    repository = make_repository(tmp_path)

    repository.record_decision(
        "так",
        ResponseCategory.CONFIRMATION,
        context="Запам'ятати фразу?",
        candidate="звісно",
        confidence=0.95,
    )
    repository.record_decision(
        "не треба",
        ResponseCategory.REJECTION,
        context="Запам'ятати фразу?",
        candidate="не потрібно",
        confidence=0.9,
    )

    with repository.session_factory() as session:
        confirmations = session.execute(
            select(ResponseConfirmation)
        ).scalars().all()
        rejections = session.execute(select(ResponseRejection)).scalars().all()

    assert [(item.response, item.candidate) for item in confirmations] == [
        ("так", "звісно")
    ]
    assert [(item.response, item.candidate) for item in rejections] == [
        ("не треба", "не потрібно")
    ]
