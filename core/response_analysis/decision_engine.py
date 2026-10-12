from __future__ import annotations

from typing import Optional

from .config import ResponseAnalysisConfig
from .models import DialogContext, ResponseAnalysis, ResponseCategory, ResponseSource
from .pattern_matcher import PatternMatcher
from .semantic_analyzer import SemanticAnalyzer
from .text_normalizer import TextNormalizer


class DecisionEngine:
    UNCERTAINTY_PHRASES = (
        "не впевнений",
        "не впевнена",
        "не впевнено",
        "не знаю",
        "важко сказати",
        "можливо",
        "мабуть",
    )
    PERMISSION_CONFIRMATION_PHRASES = (
        "можеш відкривати",
        "можеш відкрити",
        "можете відкривати",
        "можете відкрити",
        "можеш запускати",
        "можеш запустити",
        "можете запускати",
        "можете запустити",
    )

    def __init__(
        self,
        repository,
        pattern_matcher: Optional[PatternMatcher] = None,
        semantic_analyzer: Optional[SemanticAnalyzer] = None,
        config: Optional[ResponseAnalysisConfig] = None,
    ):
        self.repository = repository
        self.pattern_matcher = pattern_matcher or PatternMatcher(repository, config)
        self.semantic_analyzer = semantic_analyzer or SemanticAnalyzer(repository, config)
        self.config = config or ResponseAnalysisConfig()

    @staticmethod
    def _contains_negation(text: str) -> bool:
        lowered = TextNormalizer.normalize(text)
        negation_phrases = (
            "не хочу",
            "не треба",
            "не потрібно",
            "я передумав",
            "скасуй",
            "ні",
            "та ні",
            "не зараз",
            "не сейчас",
        )
        return any(phrase in lowered for phrase in negation_phrases)

    @staticmethod
    def _contains_confirmation(text: str) -> bool:
        lowered = TextNormalizer.normalize(text)
        positive_phrases = (
            "так",
            "ага",
            "угу",
            "добре",
            "звичайно",
            "давай",
            "можна",
        ) + DecisionEngine.PERMISSION_CONFIRMATION_PHRASES
        return any(phrase in lowered for phrase in positive_phrases)

    def decide(self, text: str, dialog_context: Optional[DialogContext] = None):
        normalized = TextNormalizer.normalize(text)
        expected = (
            dialog_context.expected_response_categories
            if dialog_context is not None
            else (ResponseCategory.CONFIRMATION, ResponseCategory.REJECTION)
        )

        if any(phrase in normalized for phrase in self.UNCERTAINTY_PHRASES):
            return ResponseAnalysis(
                ResponseCategory.UNKNOWN,
                0.0,
                None,
                ResponseSource.UNKNOWN,
            )

        if self._contains_negation(normalized) and self._contains_confirmation(normalized):
            return ResponseAnalysis(ResponseCategory.REJECTION, 0.82, None, ResponseSource.UNKNOWN)

        if ResponseCategory.CONFIRMATION in expected:
            permission_phrase = next(
                (
                    phrase
                    for phrase in self.PERMISSION_CONFIRMATION_PHRASES
                    if phrase in normalized
                ),
                None,
            )
            if permission_phrase is not None:
                return ResponseAnalysis(
                    ResponseCategory.CONFIRMATION,
                    0.9,
                    permission_phrase,
                    ResponseSource.RULE,
                )

        exact = self.pattern_matcher.match(normalized, tuple(expected))
        if exact is not None:
            return exact

        semantic = self.semantic_analyzer.analyze(normalized, tuple(expected))
        if semantic.category != ResponseCategory.UNKNOWN:
            return semantic

        return ResponseAnalysis(ResponseCategory.UNKNOWN, semantic.confidence, None, ResponseSource.UNKNOWN)
