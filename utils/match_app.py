import difflib
import re

from utils.transliterate import transliterate
from utils.categorize import guess_category

from .list_apps import get_list_installed_apps
from core.models import AppCommand


THRESHOLD = 0.6
MIN_MATCH_MARGIN = 0.05
FUZZY_TOKEN_PENALTY = 0.15
APP_KIND_PREFIX = re.compile(
    r"^(?:програму|програма|програми|додаток|додатки|застосунок|застосунки)\s+",
    re.IGNORECASE,
)
NON_ALPHANUMERIC = re.compile(r"[^\w]+", re.UNICODE)

def get_known_apps():
    apps = get_list_installed_apps()

    commands = AppCommand.objects.all()

    for command in commands:
        path = command.path

        if not path:
            continue

        apps[command.name] = path
    return apps

def _normalize_app_name(value: str) -> str:
    normalized = NON_ALPHANUMERIC.sub(" ", value.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _normalize_app_query(value: str) -> str:
    normalized = _normalize_app_name(value)
    while match := APP_KIND_PREFIX.match(normalized):
        normalized = normalized[match.end():].strip()
    return normalized


def _similarity(query: str, app_name: str) -> float:
    query_variants = {query, transliterate(query)}
    app_variants = {app_name, transliterate(app_name)}
    best_score = 0.0

    for query_variant in query_variants:
        for app_variant in app_variants:
            if query_variant == app_variant:
                return 1.0

            query_tokens = query_variant.split()
            app_tokens = app_variant.split()
            if query_tokens and any(
                app_tokens[index:index + len(query_tokens)] == query_tokens
                for index in range(len(app_tokens) - len(query_tokens) + 1)
            ):
                best_score = max(best_score, 0.95)
                continue

            full_name_score = difflib.SequenceMatcher(
                None, query_variant, app_variant
            ).ratio()
            best_score = max(best_score, full_name_score)

            if app_tokens:
                token_score = max(
                    difflib.SequenceMatcher(None, query_variant, token).ratio()
                    for token in app_tokens
                )
                if len(app_tokens) > len(query_tokens):
                    token_score = max(0.0, token_score - FUZZY_TOKEN_PENALTY)
                best_score = max(best_score, token_score)

    return best_score


def find_best_match(word, apps, threshold=THRESHOLD):
    if not word or not apps:
        return None, None

    formatted_word = _normalize_app_query(word)
    if not formatted_word:
        return None, None

    ranked_matches = sorted(
        (
            (_similarity(formatted_word, _normalize_app_name(name)), name)
            for name in apps
        ),
        reverse=True,
    )
    if not ranked_matches:
        return None, None

    best_ratio, best_name = ranked_matches[0]
    if best_ratio < threshold:
        return None, None

    if len(ranked_matches) > 1:
        second_ratio, _ = ranked_matches[1]
        if best_ratio < 1.0 and best_ratio - second_ratio < MIN_MATCH_MARGIN:
            return None, None

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
