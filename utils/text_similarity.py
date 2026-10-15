"""
Спільна метрика схожості рядків — відстань Левенштейна, нормалізована в 0..1.

Винесена в окремий модуль, бо використовується і в utils/match_app.py
(пошук програми), і в utils/categorize.py (вгадування категорії) —
щоб уникнути циклічного імпорту між ними.
"""


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    previous_row = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current_row = [i] + [0] * len(b)
        for j, char_b in enumerate(b, start=1):
            current_row[j] = min(
                previous_row[j] + 1,       # видалення
                current_row[j - 1] + 1,    # додавання
                previous_row[j - 1] + (char_a != char_b),  # заміна
            )
        previous_row = current_row

    return previous_row[-1]


def similarity(a: str, b: str) -> float:
    """Схожість рядків 0..1 на основі відстані Левенштейна."""
    if not a and not b:
        return 1.0
    longest = max(len(a), len(b))
    if longest == 0:
        return 0.0
    return 1 - levenshtein(a, b) / longest


def partial_similarity(a: str, b: str) -> float:
    """
    Схожість короткого рядка з НАЙКРАЩИМ відповідним "вікном" усередині
    довшого рядка — а не з рядком повністю.

    Потрібно для складених назв типу "telegram-desktop": повне порівняння
    "telegram" з "telegramdesktop" дає низьку схожість тільки через різну
    довжину, хоча "telegram" по суті ідеально входить у назву.
    """
    if not a or not b:
        return similarity(a, b)

    short, long_ = (a, b) if len(a) <= len(b) else (b, a)

    best = 0.0
    for start in range(len(long_) - len(short) + 1):
        window = long_[start:start + len(short)]
        score = similarity(short, window)
        if score > best:
            best = score

    return best
