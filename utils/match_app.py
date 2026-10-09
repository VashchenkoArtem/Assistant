import difflib

from utils.transliterate import transliterate
from utils.categorize import guess_category

from .list_apps import get_list_installed_apps
from core.models import AppCommand

THRESHOLD = 0.45

def get_known_apps():
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


def is_unknown(name, path):
    if AppCommand.objects.filter(path= path).exists() or AppCommand.objects.filter(name= name).exists():
        return False
    return True



def register_found_app(name: str, path: str) -> None:

    existing = AppCommand.objects.filter(path=path).first() or AppCommand.objects.filter(name=name).first()

    if existing:
        upgrade_category_if_unknown(existing, name)
        return

    AppCommand.objects.create(
        name=name,
        path=path,
        added_automatically=True,
        category=guess_category(name),
    )


def upgrade_category_if_unknown(command: AppCommand, name_hint: str) -> None:
    if not command.added_automatically:
        return
    if command.category != AppCommand.Category.OTHER:
        return

    guessed = guess_category(name_hint)
    if guessed != AppCommand.Category.OTHER:
        command.category = guessed
        command.save(update_fields=["category"])
