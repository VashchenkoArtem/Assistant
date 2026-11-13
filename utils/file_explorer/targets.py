import os
import platform
import re
from collections.abc import Iterable

from utils.text_similarity import partial_similarity, similarity
from utils.transliterate import transliterate


OPEN_VERB = re.compile(
    r"\b(?:відкрий|відкрити|відкривай|відкривати)\b",
    re.IGNORECASE,
)


TARGET_KIND = re.compile(
    r"^(?P<kind>файл(?:и|ів)?|документ(?:и|ів)?|"
    r"папк(?:а|у|и)?|каталог(?:и|у)?|директорі(?:я|ю|ї))\s*",
    re.IGNORECASE,
)


NEW_WINDOW_PHRASE = re.compile(
    r"\b(?:у|в)\s+(?:новому|окремому)\s+вікні\b",
    re.IGNORECASE,
)


CURRENT_FOLDER_PHRASE = re.compile(
    r"\b(?:у|в)\s+(?:(?:цій|поточній)\s+папці|"
    r"(?:цьому|поточному)\s+(?:каталозі|директорії))\b",
    re.IGNORECASE,
)


LOCATION_ALIASES = {
    "робочий стіл": "Desktop",
    "робочого столу": "Desktop",
    "завантаження": "Downloads",
    "завантаженнях": "Downloads",
    "завантажень": "Downloads",
    "документ": "Documents",
    "документа": "Documents",
    "документу": "Documents",
    "документи": "Documents",
    "документів": "Documents",
    "документах": "Documents",
    "зображення": "Pictures",
    "зображеннях": "Pictures",
    "фото": "Pictures",
    "музика": "Music",
    "відео": "Videos",
    "desktop": "Desktop",
    "downloads": "Downloads",
    "download": "Downloads",
    "documents": "Documents",
    "pictures": "Pictures",
    "music": "Music",
    "videos": "Videos",
    "домашня папка": "~",
    "мій комп'ютер": "shell:MyComputerFolder",
    "цей комп'ютер": "shell:MyComputerFolder",
    "this pc": "shell:MyComputerFolder",
    "кошик": "shell:RecycleBinFolder",
    "recycle bin": "shell:RecycleBinFolder",
    "провід": "explorer",
    "провідник": "explorer",
    "file explorer": "explorer",
    "explorer": "explorer",
    "налаштування": "ms-settings:",
    "налаштування windows": "ms-settings:",
    "параметри": "ms-settings:",
    "параметри windows": "ms-settings:",
    "settings": "ms-settings:",
}


SEARCH_FOLDER_NAMES = ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos")


MAX_SEARCH_DEPTH = 4


MAX_RESULTS = 5


SIMILARITY_THRESHOLD = 0.6


def _clean_target(value: str) -> str:
    return value.strip().strip("\"'«»").rstrip(" \t.,!?;:")


def is_current_folder_request(text: str) -> bool:
    return CURRENT_FOLDER_PHRASE.search(text) is not None


def parse_open_target_command(text: str) -> tuple[str, str, bool] | None:
    verb_match = OPEN_VERB.search(text)
    if verb_match is None:
        return None

    target = _clean_target(text[verb_match.end():])
    new_window = bool(NEW_WINDOW_PHRASE.search(target))
    target = _clean_target(NEW_WINDOW_PHRASE.sub("", target))
    target = _clean_target(CURRENT_FOLDER_PHRASE.sub("", target))
    kind_match = TARGET_KIND.match(target)
    if kind_match is not None:
        kind = "file" if kind_match.group("kind").lower().startswith(
            ("файл", "документ")
        ) else "folder"
        target = _clean_target(target[kind_match.end():])
        return kind, target, new_window

    normalized_target = re.sub(r"\s+", " ", target.lower()).strip()
    if normalized_target in LOCATION_ALIASES:
        return "folder", target, new_window
    return None


def _folder_bases() -> tuple[str, ...]:
    home = os.path.expanduser("~")
    bases = (home, os.environ.get("OneDrive", ""), os.path.join(home, "OneDrive"))
    return tuple(dict.fromkeys(base for base in bases if base))


def _standard_folder_path(name: str) -> str | None:
    for base in _folder_bases():
        candidate = os.path.join(base, name)
        if os.path.isdir(candidate):
            return candidate
    return None


def _search_roots() -> list[str]:
    roots = []
    for name in SEARCH_FOLDER_NAMES:
        path = _standard_folder_path(name)
        if path is not None:
            roots.append(path)
    return list(dict.fromkeys(roots))


def _iter_targets(root: str) -> Iterable[str]:
    root_depth = root.rstrip(os.sep).count(os.sep)
    for current_path, directories, files in os.walk(root):
        depth = current_path.rstrip(os.sep).count(os.sep) - root_depth
        directories[:] = [
            name for name in directories
            if not name.startswith(".") and name.casefold() not in {
                "appdata", "node_modules", "venv", "__pycache__"
            }
        ]
        if depth >= MAX_SEARCH_DEPTH:
            directories.clear()

        for name in directories:
            yield os.path.join(current_path, name)
        for name in files:
            yield os.path.join(current_path, name)


def _matches_target_name(path: str, target_name: str) -> bool:
    name = os.path.basename(path)
    return (
        name.casefold() == target_name.casefold()
        or os.path.splitext(name)[0].casefold() == target_name.casefold()
    )


def _normalized_name(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value.casefold(), flags=re.UNICODE).strip()


def _contains_cyrillic(value: str) -> bool:
    lowered = value.casefold()
    return any(
        "\u0430" <= ch <= "\u044f" or ch in {"\u0456", "\u0457", "\u0454", "\u0491"}
        for ch in lowered
    )


def _name_variants(value: str) -> set[str]:
    variants: set[str] = set()
    cleaned = _normalized_name(value)
    for fragment in re.findall(r"[^\W_]+", cleaned):
        if len(fragment) < 3:
            continue
        variants.add(fragment)
        transliterated = transliterate(fragment)
        if transliterated:
            variants.add(transliterated)
    return variants


def _is_expected_kind(path: str, expected_kind: str | None) -> bool:
    return (
        (expected_kind != "file" or os.path.isfile(path))
        and (expected_kind != "folder" or os.path.isdir(path))
    )


def find_file_targets(
    target: str,
    roots: Iterable[str] | None = None,
    expected_kind: str | None = None,
) -> list[str]:
    cleaned_target = _clean_target(target)
    if not cleaned_target:
        return []

    alias = LOCATION_ALIASES.get(re.sub(r"\s+", " ", cleaned_target.lower()))
    if alias == "ms-settings:":
        return [alias] if platform.system() == "Windows" else []
    if alias == "explorer":
        return [alias] if expected_kind != "file" else []
    if alias == "shell:MyComputerFolder" or alias == "shell:RecycleBinFolder":
        if expected_kind == "file":
            return []
        return [alias] if platform.system() == "Windows" else [os.path.expanduser("~")]
    if alias == "~":
        if expected_kind == "file":
            return []
        home = os.path.expanduser("~")
        return [home] if os.path.isdir(home) else []
    if alias:
        if expected_kind == "file":
            return []
        path = _standard_folder_path(alias)
        return [path] if path else []

    expanded_target = os.path.expandvars(os.path.expanduser(cleaned_target))
    if os.path.exists(expanded_target):
        if expected_kind == "file" and not os.path.isfile(expanded_target):
            return []
        if expected_kind == "folder" and not os.path.isdir(expanded_target):
            return []
        return [os.path.abspath(expanded_target)]

    target_name = os.path.basename(cleaned_target.rstrip("\\/"))
    if not target_name:
        return []

    found: list[str] = []
    seen: set[str] = set()
    for root in roots if roots is not None else _search_roots():
        if not os.path.isdir(root):
            continue
        for path in _iter_targets(root):
            if not _matches_target_name(path, target_name):
                continue
            if not _is_expected_kind(path, expected_kind):
                continue
            canonical_path = os.path.normcase(os.path.abspath(path))
            if canonical_path not in seen:
                seen.add(canonical_path)
                found.append(path)
                if len(found) >= MAX_RESULTS:
                    return found
    return found


def find_file_targets_in_folder(target: str, folder: str) -> list[str]:
    cleaned_target = _clean_target(target)
    if not cleaned_target or not os.path.isdir(folder):
        return []

    target_name = os.path.basename(cleaned_target.rstrip("\\/"))
    if not target_name:
        return []

    with os.scandir(folder) as entries:
        matches = sorted(
            (
                entry.path
                for entry in entries
                if entry.is_file(follow_symlinks=False)
                and _matches_target_name(entry.path, target_name)
            ),
            key=str.casefold,
        )
    return matches[:MAX_RESULTS]


def find_similar_file_targets(
    target: str,
    roots: Iterable[str] | None = None,
    expected_kind: str | None = None,
) -> list[str]:
    target_name = os.path.basename(_clean_target(target).rstrip("\\/"))
    query = _normalized_name(os.path.splitext(target_name)[0])
    if len(query) < 3:
        return []

    ranked: list[tuple[float, str]] = []
    seen: set[str] = set()
    ranked_paths: set[str] = set()
    for root in roots if roots is not None else _search_roots():
        if not os.path.isdir(root):
            continue
        for path in _iter_targets(root):
            if not _is_expected_kind(path, expected_kind):
                continue
            canonical_path = os.path.normcase(os.path.abspath(path))
            if canonical_path in seen:
                continue
            seen.add(canonical_path)

            candidate_name = os.path.basename(path)
            if os.path.isfile(path):
                candidate_name = os.path.splitext(candidate_name)[0]
            candidate = _normalized_name(candidate_name)
            if len(candidate) < 3:
                continue

            score = max(
                similarity(query, candidate),
                partial_similarity(query, candidate),
                *[
                    similarity(q_variant, c_variant)
                    for q_variant in _name_variants(query)
                    for c_variant in _name_variants(candidate)
                ],
            )
            if candidate.startswith(query):
                score = max(score, 0.9)
            candidate_threshold = (
                0.5 if _contains_cyrillic(query) ^ _contains_cyrillic(candidate) else SIMILARITY_THRESHOLD
            )
            if score >= candidate_threshold:
                ranked.append((score, path))
                ranked_paths.add(canonical_path)

    if expected_kind != "file":
        for alias, folder_name in LOCATION_ALIASES.items():
            if folder_name not in SEARCH_FOLDER_NAMES:
                continue

            path = _standard_folder_path(folder_name)
            if path is None or not _is_expected_kind(path, expected_kind):
                continue
            canonical_path = os.path.normcase(os.path.abspath(path))
            if canonical_path in ranked_paths:
                continue

            candidate = _normalized_name(alias)
            if len(candidate) < 3:
                continue
            score = max(
                similarity(query, candidate),
                partial_similarity(query, candidate),
                *[
                    similarity(q_variant, c_variant)
                    for q_variant in _name_variants(query)
                    for c_variant in _name_variants(candidate)
                ],
            )
            if candidate.startswith(query):
                score = max(score, 0.9)
            if score >= SIMILARITY_THRESHOLD:
                ranked.append((score, path))
                ranked_paths.add(canonical_path)

    ranked.sort(key=lambda item: (-item[0], item[1].casefold()))
    return [path for _score, path in ranked[:MAX_RESULTS]]
