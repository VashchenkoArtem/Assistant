import difflib

from utils.transliterate import transliterate

from .list_apps import get_list_installed_apps
from core.models import AppCommand


THRESHOLD = 0.45

def get_known_app():
    apps = get_list_installed_apps()

    commands = AppCommand.objects.all()

    for command in commands:
        path = command.path

        if not path:
            continue

        apps[command.name] = path
    return apps

def find_best_match(word, apps, threshold):
    if not word or not apps:
        return None, None

    formatted_word = word.lower().strip()
    word_translite = transliterate(formatted_word)
    
    best_name = None
    best_ratio = 0.0

    for name in apps:
        lowered_name = name.lower()
        ratio = max(
            difflib.SequenceMatcher(None, word, lowered_name).ratio(),
            difflib.SequenceMatcher(None, word_translite, lowered_name).ratio(),
        )
        if ratio > best_ratio:
            best_ratio = ratio
            best_name = name
    if best_name is not None and best_ratio >= threshold:
        return best_name, apps[best_name]