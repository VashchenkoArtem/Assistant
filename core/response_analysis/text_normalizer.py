import re


class TextNormalizer:
    @staticmethod
    def normalize(text: str) -> str:
        if text is None:
            return ""
        normalized = str(text).strip().lower()
        normalized = normalized.replace("’", "'")
        normalized = re.sub(r"[!?.]+", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    @staticmethod
    def normalize_for_match(text: str) -> str:
        return TextNormalizer.normalize(text)
