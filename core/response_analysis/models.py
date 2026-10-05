from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

from sqlalchemy import Column, Float, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ResponseCategory(str, Enum):
    CONFIRMATION = "CONFIRMATION"
    REJECTION = "REJECTION"
    UNKNOWN = "UNKNOWN"


class DialogState(str, Enum):
    IDLE = "IDLE"
    WAITING_FOR_RESPONSE = "WAITING_FOR_RESPONSE"
    WAITING_FOR_LEARNING_CONFIRMATION = "WAITING_FOR_LEARNING_CONFIRMATION"


class ResponseSource(str, Enum):
    PATTERN = "PATTERN"
    SEMANTIC = "SEMANTIC"
    UNKNOWN = "UNKNOWN"


class ResponsePattern(Base):
    __tablename__ = "response_patterns"

    id = Column(Integer, primary_key=True)
    pattern = Column(String(120), unique=True, nullable=False)
    category = Column(String(32), nullable=False)
    confidence = Column(Float, nullable=False, default=1.0)

    def __repr__(self) -> str:
        return f"ResponsePattern(pattern={self.pattern!r}, category={self.category!r})"


@dataclass
class DialogContext:
    state: DialogState = DialogState.IDLE
    question: str = ""
    pending_action: str = ""
    expected_response_categories: Sequence[ResponseCategory] = field(
        default_factory=lambda: (ResponseCategory.CONFIRMATION, ResponseCategory.REJECTION)
    )


@dataclass
class ResponseAnalysis:
    category: ResponseCategory
    confidence: float
    matched_pattern: Optional[str] = None
    source: ResponseSource = ResponseSource.UNKNOWN


@dataclass
class ResponseCandidate:
    text: str
    category: ResponseCategory
    confidence: float
