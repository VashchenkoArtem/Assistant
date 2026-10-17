from __future__ import annotations

from typing import Iterable, Optional

from django.conf import settings
from sqlalchemy import URL, create_engine, select
from sqlalchemy.orm import sessionmaker

from .config import DEFAULT_CONFIG
from .models import (
    Base,
    ResponseCategory,
    ResponseConfirmation,
    ResponsePattern,
    ResponseRejection,
)


class ResponseRepository:
    def __init__(self, database_url: str | URL | None = None):
        if database_url is None:
            database_url = URL.create(
                "sqlite",
                database=str(settings.DATABASES["default"]["NAME"]),
            )
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.seed_default_patterns()

    def seed_default_patterns(self) -> None:
        with self.session_factory() as session:
            defaults = [
                ("так", ResponseCategory.CONFIRMATION, 1.0),
                ("да", ResponseCategory.CONFIRMATION, 1.0),
                ("ага", ResponseCategory.CONFIRMATION, 1.0),
                ("угу", ResponseCategory.CONFIRMATION, 1.0),
                ("добре", ResponseCategory.CONFIRMATION, 1.0),
                ("гаразд", ResponseCategory.CONFIRMATION, 1.0),
                ("звичайно", ResponseCategory.CONFIRMATION, 1.0),
                ("звісно", ResponseCategory.CONFIRMATION, 1.0),
                ("авжеж", ResponseCategory.CONFIRMATION, 1.0),
                ("давай", ResponseCategory.CONFIRMATION, 1.0),
                ("можна", ResponseCategory.CONFIRMATION, 1.0),
                ("нехай", ResponseCategory.CONFIRMATION, 1.0),
                ("правильно", ResponseCategory.CONFIRMATION, 1.0),
                ("точно", ResponseCategory.CONFIRMATION, 1.0),
                ("вірно", ResponseCategory.CONFIRMATION, 1.0),
                ("згоден", ResponseCategory.CONFIRMATION, 1.0),
                ("згодна", ResponseCategory.CONFIRMATION, 1.0),
                ("згодні", ResponseCategory.CONFIRMATION, 1.0),
                ("погоджуюсь", ResponseCategory.CONFIRMATION, 1.0),
                ("погоджуюся", ResponseCategory.CONFIRMATION, 1.0),
                ("ок", ResponseCategory.CONFIRMATION, 1.0),
                ("окей", ResponseCategory.CONFIRMATION, 1.0),
                ("okay", ResponseCategory.CONFIRMATION, 1.0),
                ("yes", ResponseCategory.CONFIRMATION, 1.0),
                ("так так", ResponseCategory.CONFIRMATION, 1.0),

                ("ні", ResponseCategory.REJECTION, 1.0),
                ("ніт", ResponseCategory.REJECTION, 1.0),
                ("не", ResponseCategory.REJECTION, 1.0),
                ("нє", ResponseCategory.REJECTION, 1.0),
                ("неа", ResponseCategory.REJECTION, 1.0),
                ("нет", ResponseCategory.REJECTION, 1.0),
                ("no", ResponseCategory.REJECTION, 1.0),
                ("не хочу", ResponseCategory.REJECTION, 1.0),
                ("не треба", ResponseCategory.REJECTION, 1.0),
                ("не потрібно", ResponseCategory.REJECTION, 1.0),
                ("неправильно", ResponseCategory.REJECTION, 1.0),
                ("не правильно", ResponseCategory.REJECTION, 1.0),
                ("ні ні", ResponseCategory.REJECTION, 1.0),
                ("зовсім ні", ResponseCategory.REJECTION, 1.0),
                ("відміна", ResponseCategory.REJECTION, 1.0),
                ("відміни", ResponseCategory.REJECTION, 1.0),
                ("скасуй", ResponseCategory.REJECTION, 1.0),
                ("скасувати", ResponseCategory.REJECTION, 1.0),
                ("не можна", ResponseCategory.REJECTION, 1.0),
                ("неможна", ResponseCategory.REJECTION, 1.0),
                ("я передумав", ResponseCategory.REJECTION, 1.0),
            ]

            existing_patterns = set(
                session.execute(select(ResponsePattern.pattern)).scalars().all()
            )
            for pattern_text, category, confidence in defaults:
                if pattern_text not in existing_patterns:
                    session.add(
                        ResponsePattern(
                            pattern=pattern_text,
                            category=category.value,
                            confidence=confidence,
                        )
                    )

            session.commit()

    def create(self, pattern: str, category: ResponseCategory | str, confidence: float = 1.0) -> ResponsePattern:
        normalized_pattern = pattern.strip().lower()
        if not normalized_pattern:
            raise ValueError("Pattern cannot be empty.")
        if len(normalized_pattern.split()) > DEFAULT_CONFIG.max_pattern_words:
            raise ValueError("Patterns must be short phrases only.")
        if len(normalized_pattern) > DEFAULT_CONFIG.max_pattern_length:
            raise ValueError("Pattern is too long to store.")

        if isinstance(category, str):
            category = ResponseCategory(category)

        with self.session_factory() as session:
            if self.exists(normalized_pattern):
                raise ValueError(f"Pattern '{normalized_pattern}' already exists.")
            item = ResponsePattern(pattern=normalized_pattern, category=category.value, confidence=confidence)
            session.add(item)
            session.commit()
            session.refresh(item)
            return item

    def record_decision(
        self,
        response: str,
        category: ResponseCategory,
        context: str = "",
        candidate: str = "",
        confidence: float = 1.0,
    ) -> ResponseConfirmation | ResponseRejection:
        response = response.strip()
        if not response:
            raise ValueError("Response cannot be empty.")
        if category == ResponseCategory.CONFIRMATION:
            decision_type = ResponseConfirmation
        elif category == ResponseCategory.REJECTION:
            decision_type = ResponseRejection
        else:
            raise ValueError("Only confirmations and rejections can be recorded.")

        with self.session_factory() as session:
            item = decision_type(
                response=response,
                context=context,
                candidate=candidate,
                confidence=confidence,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return item

    def get(self, pattern_id: int) -> Optional[ResponsePattern]:
        with self.session_factory() as session:
            return session.get(ResponsePattern, pattern_id)

    def find_by_pattern(self, pattern: str) -> Optional[ResponsePattern]:
        normalized_pattern = pattern.strip().lower()
        with self.session_factory() as session:
            return session.execute(
                select(ResponsePattern).where(ResponsePattern.pattern == normalized_pattern)
            ).scalar_one_or_none()

    def get_by_category(self, category: ResponseCategory | str) -> list[ResponsePattern]:
        if isinstance(category, str):
            category = ResponseCategory(category)
        with self.session_factory() as session:
            return list(
                session.execute(
                    select(ResponsePattern).where(ResponsePattern.category == category.value)
                ).scalars().all()
            )

    def get_all(self) -> list[ResponsePattern]:
        with self.session_factory() as session:
            return list(session.execute(select(ResponsePattern)).scalars().all())

    def exists(self, pattern: str) -> bool:
        return self.find_by_pattern(pattern) is not None

    def update(self, pattern_id: int, **updates) -> Optional[ResponsePattern]:
        with self.session_factory() as session:
            item = session.get(ResponsePattern, pattern_id)
            if item is None:
                return None
            for key, value in updates.items():
                if key == "category" and isinstance(value, str):
                    value = ResponseCategory(value).value
                setattr(item, key, value)
            session.commit()
            return item

    def delete(self, pattern_id: int) -> bool:
        with self.session_factory() as session:
            item = session.get(ResponsePattern, pattern_id)
            if item is None:
                return False
            session.delete(item)
            session.commit()
            return True

    def __iter__(self) -> Iterable[ResponsePattern]:
        return iter(self.get_all())
