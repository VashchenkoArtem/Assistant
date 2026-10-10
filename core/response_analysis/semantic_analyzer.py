from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Optional

import numpy as np

from .config import ResponseAnalysisConfig
from .models import ResponseAnalysis, ResponseCategory, ResponseSource
from .repository import ResponseRepository
from .text_normalizer import TextNormalizer

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


# клас для аналізу сематичного змісту речення 
class SemanticAnalyzer:
    # конструктор 
    def __init__(self, repository: ResponseRepository, config: Optional[ResponseAnalysisConfig] = None):
        self.repository = repository
        self.config = config or ResponseAnalysisConfig()
        self.model: SentenceTransformer | Literal[False] | None = None

    def _ensure_model(self) -> SentenceTransformer | Literal[False]:
        if self.model is not None:
            return self.model
        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        except Exception:
            self.model = False
        return self.model

    def _fallback_embedding(self, text: str, vocabulary: list[str]) -> np.ndarray:
        tokens = TextNormalizer.normalize(text).split()
        vector = np.zeros(len(vocabulary), dtype=float)
        for token in tokens:
            if token in vocabulary:
                vector[vocabulary.index(token)] = 1.0
        return vector

    def _encode(self, text: str, vocabulary: Optional[list[str]] = None) -> np.ndarray:
        model = self._ensure_model()
        if model is not False:
            if vocabulary is None:
                return np.asarray(model.encode([text], convert_to_numpy=True)[0], dtype=float)
            encoded = np.asarray(model.encode([text], convert_to_numpy=True)[0], dtype=float)
            if encoded.size == 0:
                return self._fallback_embedding(text, vocabulary)
            return encoded

        if vocabulary is None:
            vocabulary = []
        return self._fallback_embedding(text, vocabulary)

    def analyze(self, text: str, expected_categories: Optional[tuple[ResponseCategory, ...]] = None):
        normalized = TextNormalizer.normalize(text)
        if not normalized:
            return ResponseAnalysis(ResponseCategory.UNKNOWN, 0.0, None, ResponseSource.UNKNOWN)

        patterns = self.repository.get_all()
        if not patterns:
            return ResponseAnalysis(ResponseCategory.UNKNOWN, 0.0, None, ResponseSource.UNKNOWN)

        expected = set(expected_categories or (ResponseCategory.CONFIRMATION, ResponseCategory.REJECTION))
        filtered_patterns = [pattern for pattern in patterns if ResponseCategory(pattern.category) in expected]
        if not filtered_patterns:
            return ResponseAnalysis(ResponseCategory.UNKNOWN, 0.0, None, ResponseSource.UNKNOWN)

        vocabulary = sorted({token for pattern in filtered_patterns for token in pattern.pattern.lower().split()})
        response_vector = self._encode(normalized, vocabulary)

        scored: dict[ResponseCategory, tuple[float, str]] = {}
        for pattern in filtered_patterns:
            candidate_vector = self._encode(pattern.pattern.lower(), vocabulary)
            if candidate_vector.size == 0 or response_vector.size == 0:
                similarity = 0.0
            else:
                similarity = float(np.dot(response_vector, candidate_vector) / (
                    np.linalg.norm(response_vector) * np.linalg.norm(candidate_vector)
                ))
            if np.isnan(similarity):
                similarity = 0.0
            category = ResponseCategory(pattern.category)
            scored.setdefault(category, (0.0, ""))
            if similarity > scored[category][0]:
                scored[category] = (float(similarity), pattern.pattern)

        if not scored:
            return ResponseAnalysis(ResponseCategory.UNKNOWN, 0.0, None, ResponseSource.UNKNOWN)

        best_category, (best_score, matched_pattern) = max(scored.items(), key=lambda item: item[1][0])
        second_best = sorted(score for score, _ in scored.values())
        second_score = second_best[-2] if len(second_best) > 1 else 0.0

        if best_score < self.config.semantic_min_threshold:
            return ResponseAnalysis(ResponseCategory.UNKNOWN, best_score, None, ResponseSource.UNKNOWN)

        if best_score >= self.config.semantic_high_threshold and (best_score - second_score) >= self.config.min_conflict_margin:
            return ResponseAnalysis(best_category, best_score, matched_pattern, ResponseSource.SEMANTIC)

        return ResponseAnalysis(ResponseCategory.UNKNOWN, best_score, None, ResponseSource.UNKNOWN)
