import os
import platform
import subprocess
import threading
from collections.abc import Iterable

from utils.file_explorer.models import ExplorerTab, ExplorerWindow
from utils.file_explorer.operations import (
    open_folder_in_new_tab,
    open_folder_in_new_window,
    open_target,
)
from utils.file_explorer.targets import (
    CURRENT_FOLDER_PHRASE,
    FileSearchTimeoutError,
    FILE_SEARCH_TIMEOUT_SECONDS,
    LOCATION_ALIASES,
    MAX_RESULTS,
    MAX_SEARCH_DEPTH,
    NEW_WINDOW_PHRASE,
    OPEN_VERB,
    SEARCH_FOLDER_NAMES,
    SIMILARITY_THRESHOLD,
    TARGET_KIND,
    _clean_target,
    _contains_cyrillic,
    _folder_bases,
    _is_expected_kind,
    _iter_targets,
    _matches_target_name,
    _name_variants,
    _normalized_name,
    _raise_if_cancelled,
    _resolve_search_deadline,
    _search_roots,
    _standard_folder_path,
    find_file_targets,
    find_file_targets_in_folder,
    find_similar_file_targets,
    is_current_folder_request,
    parse_find_file_command,
    parse_open_target_command,
)


def find_named_file_targets(
    target: str,
    roots: Iterable[str] | None = None,
    cancellation_event: threading.Event | None = None,
    deadline: float | None = None,
) -> list[str]:
    deadline = _resolve_search_deadline(deadline)
    _raise_if_cancelled(cancellation_event, deadline)

    cleaned_target = _clean_target(target)
    if not cleaned_target:
        return []

    expanded_target = os.path.expandvars(os.path.expanduser(cleaned_target))
    if os.path.isfile(expanded_target):
        return [os.path.abspath(expanded_target)]

    target_name = os.path.basename(cleaned_target.rstrip("\\/"))
    if not target_name:
        return []

    found: list[str] = []
    seen: set[str] = set()
    search_roots = roots if roots is not None else _folder_bases()
    for root in search_roots:
        _raise_if_cancelled(cancellation_event, deadline)
        if not os.path.isdir(root):
            continue
        for path in _iter_targets(
            root,
            cancellation_event=cancellation_event,
            max_depth=None,
            deadline=deadline,
        ):
            _raise_if_cancelled(cancellation_event, deadline)
            if not os.path.isfile(path) or not _matches_target_name(path, target_name):
                continue
            canonical_path = os.path.normcase(os.path.abspath(path))
            if canonical_path in seen:
                continue
            seen.add(canonical_path)
            found.append(path)
            if len(found) >= MAX_RESULTS:
                return found
    return found


from utils.file_explorer.windows import (
    _active_explorer_window_script,
    _run_explorer_script,
    _run_explorer_script_with_env,
    close_explorer_window,
    close_explorer_tab,
    close_explorer_windows,
    find_open_explorer_folders,
    get_active_explorer_path,
    get_active_explorer_subfolders,
    get_open_explorer_tabs,
    get_open_explorer_windows,
    navigate_explorer_back,
    navigate_explorer_to,
)
