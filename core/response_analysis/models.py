from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


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
    RULE = "RULE"
    UNKNOWN = "UNKNOWN"


class ResponsePattern(Base):
    __tablename__ = "response_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pattern: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    open_counter: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

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
