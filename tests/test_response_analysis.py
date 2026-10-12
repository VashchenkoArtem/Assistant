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


def make_repository(tmp_path):
    db_path = tmp_path / "response_patterns.db"
    return ResponseRepository(f"sqlite:///{db_path}")


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


def test_repository_seeds_missing_defaults_without_removing_user_patterns(tmp_path):
    repository = make_repository(tmp_path)
    user_pattern = "мій власний шаблон"
    repository.create(user_pattern, ResponseCategory.CONFIRMATION)

    for pattern in repository.get_all():
        if pattern.pattern != user_pattern:
            repository.delete(pattern.id)

    repository.seed_default_patterns()

    patterns = {pattern.pattern for pattern in repository.get_all()}
    assert user_pattern in patterns
    assert {"так", "ні", "ага", "не хочу"} <= patterns


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
