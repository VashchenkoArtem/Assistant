TABLE = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d",
    "е": "e", "є": "ie", "ж": "zh", "з": "z", "и": "y", "і": "i",
    "ї": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ь": "", "ю": "iu", "я": "ia", "'": "", "’": "",
}


def transliterate(text: str, g_variant: bool = False) -> str:
    table = TABLE if not g_variant else {**TABLE, "г": "g"}
    return "".join(table.get(ch, ch) for ch in text.lower())


def transliterate_variants(text: str) -> set[str]:
    """Повертає всі варіанти транслітерації + оригінальний текст (lower)."""
    return {
        text.lower(),
        transliterate(text, g_variant=False),
        transliterate(text, g_variant=True),
    }
 
