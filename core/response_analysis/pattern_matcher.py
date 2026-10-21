from __future__ import annotations

from typing import Optional

from .config import ResponseAnalysisConfig
from .models import ResponseAnalysis, ResponseCategory, ResponseSource
from .repository import ResponseRepository
from .text_normalizer import TextNormalizer


class PatternMatcher:
    def __init__(self, repository: ResponseRepository, config: Optional[ResponseAnalysisConfig] = None):
        self.repository = repository
        self.config = config or ResponseAnalysisConfig()

    def match(self, text: str, expected_categories: Optional[tuple[ResponseCategory, ...]] = None):
        normalized = TextNormalizer.normalize(text)
        if not normalized:
            return None

        candidate_patterns = self.repository.get_all()
        if not candidate_patterns:
            return None

        expected = set(expected_categories or (ResponseCategory.CONFIRMATION, ResponseCategory.REJECTION))

        best_match = None
        best_score = -1.0

        for pattern in candidate_patterns:
            pattern_category = ResponseCategory(pattern.category)
            if expected and pattern_category not in expected:
                continue

            candidate_text = pattern.pattern.lower().strip()

            if candidate_text == normalized:
                score = self.config.exact_match_confidence
                if score > best_score:
                    best_match = pattern
                    best_score = score
                continue

            if candidate_text in normalized or normalized in candidate_text:
                score = self.config.phrase_match_confidence
                if score > best_score:
                    best_match = pattern
                    best_score = score

        if best_match is None:
            return None

        return ResponseAnalysis(
            category=ResponseCategory(best_match.category),
            confidence=best_score,
            matched_pattern=best_match.pattern,
            source=ResponseSource.PATTERN,
        )
