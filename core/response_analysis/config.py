from dataclasses import dataclass


@dataclass(frozen=True)
class ResponseAnalysisConfig:
    semantic_high_threshold: float = 0.78
    semantic_min_threshold: float = 0.62
    exact_match_confidence: float = 1.0
    phrase_match_confidence: float = 0.96
    max_pattern_words: int = 4
    max_pattern_length: int = 45
    min_conflict_margin: float = 0.08


DEFAULT_CONFIG = ResponseAnalysisConfig()
