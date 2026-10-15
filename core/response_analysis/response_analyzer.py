from __future__ import annotations

from .decision_engine import DecisionEngine
from .models import DialogContext, ResponseAnalysis
from .repository import ResponseRepository


class ResponseAnalyzer:
    def __init__(self, repository: ResponseRepository, decision_engine: DecisionEngine | None = None):
        self.repository = repository
        self.decision_engine = decision_engine or DecisionEngine(repository)

    def analyze(self, question: str, answer: str, dialog_context: DialogContext | None = None) -> ResponseAnalysis:
        context = dialog_context or DialogContext()
        return self.decision_engine.decide(answer, context)
