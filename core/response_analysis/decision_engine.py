from __future__ import annotations

import re
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
    NEGATION_PHRASES = {
        "та ні",
        "я передумав",
        "не зараз",
        "не сейчас",
    }
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

    def _contains_category_pattern(
        self,
        text: str,
        category: ResponseCategory,
    ) -> bool:
        lowered = TextNormalizer.normalize(text)
        patterns = (
            pattern.pattern
            for pattern in self.repository.get_by_category(category)
        )
        return any(
            re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", lowered)
            for phrase in patterns
        )

    def _contains_negation(self, text: str) -> bool:
        lowered = TextNormalizer.normalize(text)
        return any(
            re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", lowered)
            for phrase in self.NEGATION_PHRASES
        ) or self._contains_category_pattern(text, ResponseCategory.REJECTION)

    def _contains_confirmation(self, text: str) -> bool:
        lowered = TextNormalizer.normalize(text)
        return any(
            re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", lowered)
            for phrase in self.PERMISSION_CONFIRMATION_PHRASES
        ) or self._contains_category_pattern(text, ResponseCategory.CONFIRMATION)

    def decide(self, text: str, dialog_context: Optional[DialogContext] = None):
        normalized = TextNormalizer.normalize(text)
        expected = (
            dialog_context.expected_response_categories
            if dialog_context is not None
            else (ResponseCategory.CONFIRMATION, ResponseCategory.REJECTION)
        )

        clean_text = normalized.strip(".!,? ")
        clean_text = re.sub(r"[^\w\s]", " ", clean_text)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        if any(phrase in normalized for phrase in self.UNCERTAINTY_PHRASES):
            return ResponseAnalysis(
                ResponseCategory.UNKNOWN,
                0.0,
                None,
                ResponseSource.UNKNOWN,
            )

        exact = self.pattern_matcher.match(clean_text, tuple(expected), exact_only=True)
        if exact is not None:
            return exact

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

        matched_pattern = self.pattern_matcher.match(normalized, tuple(expected))
        if matched_pattern is not None:
            return matched_pattern

        semantic = self.semantic_analyzer.analyze(normalized, tuple(expected))
        if semantic.category != ResponseCategory.UNKNOWN:
            return semantic

        return ResponseAnalysis(ResponseCategory.UNKNOWN, semantic.confidence, None, ResponseSource.UNKNOWN)
