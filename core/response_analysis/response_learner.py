from __future__ import annotations

from .models import ResponseCandidate, ResponseCategory
from .repository import ResponseRepository
from .text_normalizer import TextNormalizer


class ResponseLearner:
    def __init__(self, repository: ResponseRepository):
        self.repository = repository

    def create_candidate(self, text: str, category: ResponseCategory, confidence: float) -> ResponseCandidate | None:
        normalized = TextNormalizer.normalize(text)
        if not normalized:
            return None
        if len(normalized.split()) > 4 or len(normalized) > 45:
            return None
        if self.repository.exists(normalized):
            return None
        return ResponseCandidate(text=normalized, category=category, confidence=confidence)

    def accept_candidate(self, candidate: ResponseCandidate):
        return self.repository.create(candidate.text, candidate.category, candidate.confidence)

    def reject_candidate(self, candidate: ResponseCandidate) -> bool:
        return True
