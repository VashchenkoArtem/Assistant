from core.models import AppCommand
from utils.text_similarity import partial_similarity
from utils.transliterate import transliterate_variants


CATEGORY_THRESHOLD = 0.7

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    AppCommand.Category.BROWSER: (
        "chrome", "firefox", "edge", "opera", "brave", "safari",
        "yandex", "vivaldi", "browser",
    ),
    AppCommand.Category.MESSENGER: (
        "telegram", "discord", "skype", "slack", "whatsapp", "viber",
        "messenger", "signal", "teams",
    ),
    AppCommand.Category.GAME: (
        "steam", "epicgames", "battlenet", "origin", "uplay",
        "ubisoft", "gog", "riotclient", "minecraft", "playstation",
    ),
    AppCommand.Category.MEDIA: (
        "spotify", "vlc", "itunes", "winamp", "musicbee", "obs",
        "premiere", "audacity",
    ),
    AppCommand.Category.DEV_TOOL: (
        "code", "pycharm", "intellij", "sublime", "webstorm",
        "androidstudio", "docker", "git", "terminal", "powershell",
        "postman", "datagrip",
    ),
    AppCommand.Category.UTILITY: (
        "notepad", "calculator", "paint", "winrar", "7zip",
        "explorer", "taskmanager", "cleaner",
    ),
}


def guess_category(name: str) -> str:
    candidates = {name.lower().replace(" ", "").replace("-", "")} | {
        v.replace(" ", "").replace("-", "") for v in transliterate_variants(name)
    }

    best_category = AppCommand.Category.OTHER
    best_score = 0.0

    for category, keywords in _CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            for candidate in candidates:
                score = partial_similarity(candidate, keyword)
                if score > best_score:
                    best_score, best_category = score, category

    return best_category if best_score >= CATEGORY_THRESHOLD else AppCommand.Category.OTHER
    
    
