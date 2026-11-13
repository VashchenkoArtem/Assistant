import os
import platform
import subprocess

from utils.file_explorer.models import ExplorerTab, ExplorerWindow
from utils.file_explorer.operations import (
    open_folder_in_new_tab,
    open_folder_in_new_window,
    open_target,
)
from utils.file_explorer.targets import (
    CURRENT_FOLDER_PHRASE,
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
    _search_roots,
    _standard_folder_path,
    find_file_targets,
    find_file_targets_in_folder,
    find_similar_file_targets,
    is_current_folder_request,
    parse_open_target_command,
)
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
