from core.models import AppCommand

CATEGORY_THRESHOLD = 0.7

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
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

def guess_category(name: str):

    best_category = AppCommand.Category.OTHER
    best_ratio = 0.0

    
    