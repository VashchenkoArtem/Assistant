import os
from unittest.mock import Mock, patch

import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Assistant.settings")

import django

django.setup()

from core.management.commands import run_assistant
from core.management.commands.run_assistant import Command
from core.response_analysis import ResponseAnalysis, ResponseCategory, ResponseSource
from utils.file_explorer import (
    ExplorerTab,
    ExplorerWindow,
    close_explorer_window,
    close_explorer_tab,
    close_explorer_windows,
    find_open_explorer_folders,
    get_open_explorer_tabs,
    get_open_explorer_windows,
    find_file_targets,
    find_file_targets_in_folder,
    find_similar_file_targets,
    get_active_explorer_path,
    get_active_explorer_subfolders,
    is_current_folder_request,
    navigate_explorer_back,
    navigate_explorer_to,
    open_target,
    parse_open_target_command,
)


def make_command():
    command = Command()
    command.pending_app = None
    command.pending_learning_candidate = None
    command.pending_file = None
    return command


@pytest.mark.parametrize(
    ("spoken_text", "expected"),
    [
        ("Відкрий файл звіт.docx", ("file", "звіт.docx", False)),
        ("Відкрий папку Завантаження", ("folder", "Завантаження", False)),
        ("Відкрий провід", ("folder", "провід", False)),
        ("Відкрий провідник", ("folder", "провідник", False)),
        ("Відкрий файл", ("file", "", False)),
        (
            "Відкрий файл звіт.docx у поточній папці",
            ("file", "звіт.docx", False),
        ),
        (
            "Відкрий папку Завантаження у новому вікні",
            ("folder", "Завантаження", True),
        ),
        (
            "Відкрий у новому вікні папку Завантаження",
            ("folder", "Завантаження", True),
        ),
        ("Відкрий програму Steam", None),
    ],
)
def test_parse_open_target_command(spoken_text, expected):
    assert parse_open_target_command(spoken_text) == expected


def test_find_file_target_by_path_and_by_name(tmp_path):
    target = tmp_path / "звіт.docx"
    target.write_text("test", encoding="utf-8")

    assert find_file_targets(str(target), expected_kind="file") == [str(target)]
    assert find_file_targets(
        target.name,
        roots=[str(tmp_path)],
        expected_kind="file",
    ) == [str(target)]


def test_find_file_target_without_extension(tmp_path):
    target = tmp_path / "звіт.docx"
    target.touch()

    assert find_file_targets(
        "звіт",
        roots=[str(tmp_path)],
        expected_kind="file",
    ) == [str(target)]


def test_find_file_target_only_searches_direct_children_of_current_folder(tmp_path):
    current = tmp_path / "current"
    nested = current / "nested"
    nested.mkdir(parents=True)
    direct_file = current / "report.docx"
    nested_file = nested / "report.docx"
    direct_file.touch()
    nested_file.touch()

    assert find_file_targets_in_folder("report", str(current)) == [str(direct_file)]
    assert find_file_targets_in_folder("missing.docx", str(current)) == []


def test_parse_current_folder_request_preserves_explicit_scope():
    spoken_text = "Відкрити файл report.docx у поточній папці"

    assert is_current_folder_request(spoken_text)
    assert parse_open_target_command(spoken_text) == (
        "file",
        "report.docx",
        False,
    )


@pytest.mark.parametrize(
    "spoken_text",
    [
        "Відкрити файл report.docx у цій папці",
        "Відкрити файл report.docx в поточному каталозі",
    ],
)
def test_parse_current_folder_request_accepts_synonyms(spoken_text):
    assert is_current_folder_request(spoken_text)


def test_settings_alias_resolves_to_windows_settings(monkeypatch):
    monkeypatch.setattr("utils.file_explorer.platform.system", lambda: "Windows")

    assert parse_open_target_command("відкрити налаштування") == (
        "folder",
        "налаштування",
        False,
    )
    assert find_file_targets("налаштування", expected_kind="folder") == [
        "ms-settings:"
    ]


def test_open_target_launches_windows_settings(monkeypatch):
    startfile = Mock()
    monkeypatch.setattr("utils.file_explorer.platform.system", lambda: "Windows")
    monkeypatch.setattr("utils.file_explorer.os.startfile", startfile, raising=False)

    open_target("ms-settings:")

    startfile.assert_called_once_with("ms-settings:")


@pytest.mark.parametrize(
    "spoken_folder",
    ["документи", "документів", "документа", "документу", "документах"],
)
def test_document_folder_alias_accepts_inflected_forms(monkeypatch, spoken_folder):
    documents_path = r"C:\Users\test\Documents"
    resolve_folder = Mock(return_value=documents_path)
    monkeypatch.setattr(
        "utils.file_explorer.targets._standard_folder_path",
        resolve_folder,
    )

    assert find_file_targets(spoken_folder, expected_kind="folder") == [documents_path]
    resolve_folder.assert_called_once_with("Documents")


def test_find_file_target_filters_out_wrong_kind(tmp_path):
    folder = tmp_path / "Документи"
    folder.mkdir()

    assert find_file_targets(str(folder), expected_kind="file") == []


def test_find_similar_file_targets_suggests_close_file_names(tmp_path):
    target = tmp_path / "теория.docx"
    target.touch()

    assert find_file_targets("теорія", roots=[str(tmp_path)], expected_kind="file") == []
    assert find_similar_file_targets(
        "теорія",
        roots=[str(tmp_path)],
        expected_kind="file",
    ) == [str(target)]


def test_find_similar_file_targets_matches_cyrillic_and_latin_folder_names(tmp_path):
    target = tmp_path / "Codex"
    target.mkdir()

    assert find_similar_file_targets(
        "кодекс",
        roots=[str(tmp_path)],
        expected_kind="folder",
    ) == [str(target)]


def test_match_explorer_folder_name_accepts_cross_script_name(tmp_path):
    targets = [str(tmp_path / "Alpha"), str(tmp_path / "Codex")]

    assert Command._match_explorer_folder_name("кодекс", targets) == targets[1]


def test_similar_folder_search_includes_standard_folder_alias(tmp_path, monkeypatch):
    documents = tmp_path / "Documents"
    music = tmp_path / "Music"
    russian_music = documents / "Моя музыка"
    russian_music.mkdir(parents=True)
    music.mkdir()
    standard_folders = {
        "Documents": str(documents),
        "Music": str(music),
    }
    monkeypatch.setattr(
        "utils.file_explorer.targets._standard_folder_path",
        lambda name: standard_folders.get(name),
    )

    suggestions = find_similar_file_targets(
        "музики",
        roots=[str(documents), str(music)],
        expected_kind="folder",
    )

    assert suggestions == [str(music), str(russian_music)]


def test_similar_folder_search_excludes_short_names_that_match_any_substring(
    tmp_path,
    monkeypatch,
):
    for parent in ("Desktop", "ItemTemplates", "ProjectTemplates"):
        (tmp_path / parent / "C#").mkdir(parents=True)
    telegram_desktop = tmp_path / "Downloads" / "Telegram Desktop"
    telegram_desktop.mkdir(parents=True)
    monkeypatch.setattr(
        "utils.file_explorer.targets._standard_folder_path",
        lambda _name: None,
    )

    suggestions = find_similar_file_targets(
        "Telegram Tech",
        roots=[str(tmp_path)],
        expected_kind="folder",
    )

    assert suggestions == [str(telegram_desktop)]


def test_ambiguous_voice_target_requires_numbered_selection(tmp_path):
    first = tmp_path / "Персональна папка" / "звіт.docx"
    second = tmp_path / "Робоча папка" / "звіт.docx"
    first.parent.mkdir()
    second.parent.mkdir()
    first.touch()
    second.touch()

    command = make_command()
    with (
        patch.object(run_assistant, "find_file_targets", return_value=[str(first), str(second)]),
        patch.object(run_assistant, "open_target") as open_target,
        patch.object(run_assistant, "voicing_and_printing_answer"),
    ):
        command.handle_file_open("file", "звіт.docx")

        pending_file = command.pending_file
        assert pending_file is not None
        assert pending_file["awaiting_selection"] is True
        open_target.assert_not_called()

        command.doing_task("я обираю номер два")

        pending_file = command.pending_file
        assert pending_file is not None
        assert pending_file["awaiting_selection_confirmation"] is True
        open_target.assert_not_called()

        command.analyze_response = Mock(
            return_value=ResponseAnalysis(
                ResponseCategory.CONFIRMATION,
                1.0,
                source=ResponseSource.PATTERN,
            )
        )
        command.doing_task("так")

    open_target.assert_called_once_with(str(second))
    assert command.pending_file is None


def test_out_of_range_file_number_is_ignored_and_selection_reprompted(tmp_path):
    paths = [str(tmp_path / "one.docx"), str(tmp_path / "two.docx")]
    command = make_command()
    command.pending_file = {
        "awaiting_selection": True,
        "targets": paths,
    }

    with patch.object(run_assistant, "voicing_and_printing_answer") as speak:
        command.doing_task("варіант 7")

    pending_file = command.pending_file
    assert pending_file is not None
    assert pending_file["awaiting_selection"] is True
    assert "Не розпізнала вибір" in speak.call_args.args[0]
    assert command.pending_file["targets"] == paths


def test_rejecting_file_selection_confirmation_returns_to_options(tmp_path):
    paths = [str(tmp_path / "one.docx"), str(tmp_path / "two.docx")]
    command = make_command()
    command.pending_file = {
        "awaiting_selection_confirmation": True,
        "targets": paths,
        "selected_target": paths[0],
    }
    command.analyze_response = Mock(
        return_value=ResponseAnalysis(
            ResponseCategory.REJECTION,
            1.0,
            source=ResponseSource.PATTERN,
        )
    )

    with patch.object(run_assistant, "voicing_and_printing_answer"):
        command.doing_task("ні")

    assert command.pending_file["awaiting_selection"] is True
    assert command.pending_file["awaiting_selection_confirmation"] is False
    assert "selected_target" not in command.pending_file
def test_file_open_command_uses_default_application(tmp_path):
    target = tmp_path / "звіт.docx"
    target.touch()
    command = make_command()

    with (
        patch.object(run_assistant, "open_target") as open_target,
        patch.object(run_assistant, "voicing_and_printing_answer"),
    ):
        command.doing_task(f"відкрий файл {target}")

    open_target.assert_called_once_with(str(target))


@pytest.mark.parametrize("spoken_name", ["Провідник", "провід"])
def test_open_explorer_voice_command_launches_file_manager(spoken_name):
    command = make_command()

    with (
        patch.object(run_assistant, "open_target") as open_target,
        patch.object(run_assistant, "get_known_apps") as get_known_apps,
        patch.object(run_assistant, "voicing_and_printing_answer"),
    ):
        command.doing_task(f"відкрий {spoken_name}")

    open_target.assert_called_once_with("explorer")
    get_known_apps.assert_not_called()


def test_folder_opens_in_new_tab_of_existing_explorer_window(tmp_path):
    folder = tmp_path / "Документи"
    folder.mkdir()
    completed = Mock(returncode=0, stdout="opened-tab\n", stderr="")

    with (
        patch("utils.file_explorer.platform.system", return_value="Windows"),
        patch("utils.file_explorer.subprocess.run", return_value=completed) as run,
        patch("utils.file_explorer.subprocess.Popen") as popen,
    ):
        open_target(str(folder))

    assert run.call_args.kwargs["env"]["ASSISTANT_EXPLORER_TARGET"] == str(folder)
    script = run.call_args.args[0][-1]
    assert "$target = $env:ASSISTANT_EXPLORER_TARGET" in script
    assert "[AssistantExplorerWindow]::GetAncestor(" in script
    assert "$invokePattern.Invoke()" in script
    assert "$newWindow.Navigate2($target)" in script
    assert "$existingComIds.ContainsKey($identity)" in script
    assert "'AddButton'" in script
    assert "Add New Tab" in script
    assert "Navigate2($target, 0x0800)" not in script
    assert "TypeText" not in script
    popen.assert_not_called()


def test_open_folder_reports_generic_error_without_powerShell_details():
    command = make_command()
    technical_error = "Не вдалося знайти кнопку створення вкладки Провідника."
    with (
        patch.object(run_assistant, "open_target", side_effect=RuntimeError(technical_error)),
        patch.object(run_assistant, "voicing_and_printing_answer") as answer,
        patch.object(run_assistant.logger, "warning") as warning,
        patch.object(command.stdout, "write") as write,
    ):
        command.open_file_target(r"C:\Users\test\Videos")

    answer.assert_called_once_with("Не вдалося відкрити Videos.")
    write.assert_not_called()
    warning.assert_called_once_with("Opening target failed: %s", "RuntimeError")


def test_music_alias_resolves_to_music_folder_not_home(monkeypatch, tmp_path):
    home = tmp_path / "user"
    music = home / "Music"
    music.mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("OneDrive", "")
    monkeypatch.setattr("utils.file_explorer.os.path.expanduser", lambda _path: str(home))

    assert find_file_targets("музика", expected_kind="folder") == [str(music)]


def test_folder_opens_requested_path_in_new_explorer_window(tmp_path):
    folder = tmp_path / "Мої файли" / "Python"
    folder.mkdir(parents=True)

    with (
        patch("utils.file_explorer.platform.system", return_value="Windows"),
        patch("utils.file_explorer.subprocess.Popen") as popen,
    ):
        open_target(str(folder), new_window=True)

    popen.assert_called_once_with(
        ["explorer.exe", "/n,", "/e,", os.path.abspath(folder)]
    )


def test_folder_opens_in_new_explorer_window_when_requested(tmp_path):
    folder = tmp_path / "Документи"
    folder.mkdir()

    with (
        patch("utils.file_explorer.platform.system", return_value="Windows"),
        patch("utils.file_explorer.subprocess.Popen") as popen,
        patch("utils.file_explorer.subprocess.run") as run,
    ):
        open_target(str(folder), new_window=True)

    popen.assert_called_once_with(
        ["explorer.exe", "/n,", "/e,", os.path.abspath(folder)]
    )
    run.assert_not_called()


def test_folder_opens_in_new_window_if_no_explorer_window_exists(tmp_path):
    folder = tmp_path / "Документи"
    folder.mkdir()
    completed = Mock(returncode=0, stdout="no-window\n", stderr="")

    with (
        patch("utils.file_explorer.platform.system", return_value="Windows"),
        patch("utils.file_explorer.subprocess.run", return_value=completed),
        patch("utils.file_explorer.subprocess.Popen") as popen,
    ):
        open_target(str(folder))

    popen.assert_called_once_with(["explorer.exe", str(folder)])


def test_new_window_voice_option_is_preserved_while_selecting_file_folder(tmp_path):
    folder = tmp_path / "Документи"
    folder.mkdir()
    command = make_command()

    with (
        patch.object(run_assistant, "find_file_targets", return_value=[str(folder)]),
        patch.object(run_assistant, "open_target") as open_target,
        patch.object(run_assistant, "voicing_and_printing_answer"),
    ):
        command.doing_task(f"відкрий папку {folder} у новому вікні")

    open_target.assert_called_once_with(str(folder), new_window=True)


def test_open_file_in_current_folder_uses_active_explorer_path(tmp_path):
    report = str(tmp_path / "report.docx")
    command = make_command()

    with (
        patch.object(run_assistant, "get_active_explorer_path", return_value=str(tmp_path)),
        patch.object(
            run_assistant,
            "find_file_targets_in_folder",
            return_value=[report],
        ) as find_in_current,
        patch.object(run_assistant, "open_target") as open_file,
        patch.object(run_assistant, "voicing_and_printing_answer"),
    ):
        command.doing_task("відкрити файл report.docx у поточній папці")

    find_in_current.assert_called_once_with("report.docx", str(tmp_path))
    open_file.assert_called_once_with(report)


def test_current_folder_scope_is_preserved_when_file_name_is_requested_later(
    tmp_path,
):
    report = str(tmp_path / "report.docx")
    command = make_command()

    with (
        patch.object(run_assistant, "get_active_explorer_path", return_value=str(tmp_path)),
        patch.object(
            run_assistant,
            "find_file_targets_in_folder",
            return_value=[report],
        ) as find_in_current,
        patch.object(run_assistant, "open_target") as open_file,
        patch.object(run_assistant, "voicing_and_printing_answer"),
    ):
        command.doing_task("відкрити файл у поточній папці")
        assert command.pending_file is not None
        assert command.pending_file["current_folder"] is True
        command.doing_task("report.docx")

    find_in_current.assert_called_once_with("report.docx", str(tmp_path))
    open_file.assert_called_once_with(report)


def test_open_settings_command_opens_windows_settings():
    command = make_command()

    with (
        patch.object(run_assistant, "find_file_targets", return_value=["ms-settings:"]),
        patch.object(run_assistant, "open_target") as open_settings,
        patch.object(run_assistant, "voicing_and_printing_answer"),
    ):
        command.doing_task("відкрити налаштування")

    open_settings.assert_called_once_with("ms-settings:")


@pytest.mark.parametrize(
    "spoken_text",
    [
        "закрий Провідник",
        "закрий вікна Провідника",
        "закриття Провідника",
    ],
)
def test_close_explorer_voice_command_closes_explorer_windows(spoken_text):
    command = make_command()

    with (
        patch.object(run_assistant, "close_explorer_windows", return_value=2) as close_windows,
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
    ):
        command.doing_task(spoken_text)

    close_windows.assert_called_once_with()
    assert "Закрито вікон: 2" in speak.call_args.args[0]


def test_close_explorer_reports_when_there_are_no_open_windows():
    command = make_command()

    with (
        patch.object(run_assistant, "close_explorer_windows", return_value=0),
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
    ):
        command.doing_task("закрий Провідник")

    assert "Відкритих вікон" in speak.call_args.args[0]


def test_close_all_explorer_windows_command_without_listing():
    command = make_command()
    with (
        patch.object(run_assistant, "close_explorer_windows", return_value=2) as close_all,
        patch.object(run_assistant, "voicing_and_printing_answer") as answer,
    ):
        command.doing_task("закрий всі вікна")

    close_all.assert_called_once_with()
    assert answer.call_args.args[0] == "Закрила вікна Провідника. Закрито вікон: 2."


@pytest.mark.parametrize(
    "spoken_text",
    [
        "закрий всі папки",
        "закрити усі відкриті папки",
        "закривай всі вкладки",
        "закрити всі вкладки у Провіднику",
    ],
)
def test_close_all_explorer_folders_command(spoken_text):
    command = make_command()
    with (
        patch.object(
            run_assistant, "close_explorer_windows", return_value=3
        ) as close_windows,
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
    ):
        command.doing_task(spoken_text)

    close_windows.assert_called_once_with()
    speak.assert_called_once_with(
        "Закрила всі відкриті папки. Закрито вкладок: 3."
    )


def test_close_all_explorer_folders_reports_empty_list():
    command = make_command()
    with (
        patch.object(run_assistant, "close_explorer_windows", return_value=0),
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
    ):
        command.doing_task("закрий всі папки")

    speak.assert_called_once_with("У Провіднику немає відкритих папок.")


def test_close_all_explorer_folders_hides_technical_error():
    command = make_command()
    with (
        patch.object(
            run_assistant,
            "close_explorer_windows",
            side_effect=RuntimeError("PowerShell raw error"),
        ),
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
        patch.object(run_assistant.logger, "warning") as warning,
        patch.object(command.stdout, "write") as write,
    ):
        command.doing_task("закрий всі папки")

    speak.assert_called_once_with("Не вдалося закрити відкриті папки Провідника.")
    warning.assert_called_once_with(
        "Closing all Explorer folders failed: %s", "RuntimeError"
    )
    write.assert_not_called()


def test_close_explorer_windows_only_closes_explorer_windows():
    with (
        patch("utils.file_explorer.platform.system", return_value="Windows"),
        patch(
            "utils.file_explorer.windows._run_explorer_script",
            return_value="2",
        ) as run_script,
    ):
        assert close_explorer_windows() == 2

    script = run_script.call_args.args[0]
    assert "explorer.exe" in script
    assert "Select-Object -Unique" in script
    assert "PostMessage" in script
    assert "0x0010" in script
    assert "Stop-Process" not in script


def test_get_open_explorer_windows_groups_tabs_by_hwnd():
    tabs = [
        ExplorerTab(r"C:\Users\test\Videos", "Videos", 100, 0),
        ExplorerTab(r"C:\Users\test\Documents", "Documents", 100, 1),
        ExplorerTab(r"C:\Users\test\Downloads", "Downloads", 200, 0),
    ]
    with patch(
        "utils.file_explorer.windows.get_open_explorer_tabs",
        return_value=tabs,
    ):
        assert get_open_explorer_windows() == [
            ExplorerWindow(100, tuple(tabs[:2])),
            ExplorerWindow(200, (tabs[2],)),
        ]


def test_close_explorer_window_posts_close_for_matching_explorer_hwnd():
    with patch(
        "utils.file_explorer.windows._run_explorer_script_with_env",
        return_value="closed",
    ) as run_script:
        assert close_explorer_window(100) is True

    script, env = run_script.call_args.args
    assert env == {"ASSISTANT_EXPLORER_HWND": "100"}
    assert "[int64]$_.HWND -eq $targetHwnd" in script
    assert "[AssistantExplorerWindow]::PostMessage" in script
    assert "0x0010" in script


def test_active_explorer_path_is_read_from_selected_window():
    with (
        patch(
            "utils.file_explorer.windows._run_explorer_script",
            return_value=r"C:\Users\test\Documents",
        ) as run_script,
        patch("utils.file_explorer.platform.system", return_value="Windows"),
    ):
        assert get_active_explorer_path() == os.path.normpath(
            r"C:\Users\test\Documents"
        )

    script = run_script.call_args.args[0]
    assert "GetAncestor" in script
    assert "$foregroundRoot" in script
    assert "$targetRoot" in script
    assert "matchingWindows.Count -eq 1" in script
    assert "AutomationIdProperty" in script
    assert "'TabView'" in script
    assert "SelectionItemPattern" in script
    assert "TryGetCurrentPattern" in script
    assert "TreeScope]::Children" in script
    assert script.index("TreeScope]::Children") < script.index(
        "TreeScope]::Descendants"
    )
    assert "$window = $matchingWindows[0]" in script
    assert "$matchingWindows[$selectedTabIndex]" not in script
    assert "$candidateNames -contains $selectedTabName" in script
    assert "$tabView = Get-ExplorerTabView $targetRoot" in script
    assert "$window = $namedWindows[0]" in script
    assert "fallbackToFirst" in script
    assert "finally {" in script
    assert "ReleaseComObject($shellWindow)" in script


def test_active_explorer_path_handles_virtual_shell_locations():
    with (
        patch(
            "utils.file_explorer.windows._run_explorer_script",
            return_value="shell:Home",
        ) as run_script,
        patch("utils.file_explorer.platform.system", return_value="Windows"),
    ):
        assert get_active_explorer_path() == "shell:Home"

    script = run_script.call_args.args[0]
    assert "$document = $window.Document" in script
    assert "if ($document)" in script
    assert "$window.LocationURL" in script
    assert '$path = "shell:$locationName"' in script


def test_active_explorer_subfolders_are_sorted(tmp_path):
    (tmp_path / "Zulu").mkdir()
    (tmp_path / "Alpha").mkdir()
    (tmp_path / "not-a-folder.txt").touch()

    with patch(
        "utils.file_explorer.windows.get_active_explorer_path",
        return_value=str(tmp_path),
    ):
        assert get_active_explorer_subfolders() == [
            str(tmp_path / "Alpha"),
            str(tmp_path / "Zulu"),
        ]


def test_active_explorer_subfolders_include_entries_after_the_eighth(tmp_path):
    for index in range(1, 10):
        (tmp_path / f"Folder {index}").mkdir()

    with patch(
        "utils.file_explorer.windows.get_active_explorer_path",
        return_value=str(tmp_path),
    ):
        folders = get_active_explorer_subfolders()

    assert folders is not None
    assert len(folders) == 9
    assert os.path.basename(folders[-1]) == "Folder 9"


def test_active_explorer_virtual_folder_subfolders_come_from_shell_items():
    namespace_path = "::{F874310E-B6B7-47DC-BC84-B9E6B38F5903}"
    with (
        patch(
            "utils.file_explorer.windows.get_active_explorer_path",
            return_value=namespace_path,
        ),
        patch("utils.file_explorer.os.path.isdir", return_value=False),
        patch(
            "utils.file_explorer.windows._run_explorer_script",
            return_value='["D:\\\\", "C:\\\\"]',
        ) as run_script,
    ):
        folders = get_active_explorer_subfolders()

    assert folders == ["C:\\", "D:\\"]
    script = run_script.call_args.args[0]
    assert "$document.Folder.Items()" in script
    assert "Не вдалося отримати вміст активної вкладки" in script
    assert "$_.IsFolder" in script


def test_active_explorer_virtual_folder_without_subfolders_returns_empty_list():
    with (
        patch(
            "utils.file_explorer.windows.get_active_explorer_path",
            return_value="::{F874310E-B6B7-47DC-BC84-B9E6B38F5903}",
        ),
        patch("utils.file_explorer.os.path.isdir", return_value=False),
        patch("utils.file_explorer.windows._run_explorer_script", return_value="[]"),
    ):
        assert get_active_explorer_subfolders() == []


def test_forward_navigation_reports_empty_virtual_folder_without_error():
    command = make_command()
    with (
        patch.object(run_assistant, "get_active_explorer_subfolders", return_value=[]),
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
    ):
        command.navigate_explorer_forward()

    assert "немає вкладених папок" in speak.call_args.args[0]
    assert command.pending_file is None


def test_virtual_drive_folder_name_uses_drive_label():
    assert Command._explorer_folder_name("C:\\") == "C:"


@pytest.mark.parametrize(
    "spoken_text",
    [
        "Які папки відкриті?",
        "Які вкладки зараз відкриті у Провіднику?",
        "Покажи відкриті папки",
        "Показати відкриті папки",
        "Відкриті папки",
        "Покажи список відкритих папок",
        "Перелічи мені відкриті вкладки",
        "Список відкритих папок у Провіднику",
    ],
)
def test_open_explorer_tabs_command_shows_names_and_paths(spoken_text):
    tabs = [
        ExplorerTab(r"C:\Users\test\Downloads", "Завантаження", 100, 0),
        ExplorerTab(r"C:\Users\test\Documents", "Документи", 200, 0),
    ]
    command = make_command()

    with (
        patch.object(run_assistant, "get_open_explorer_tabs", return_value=tabs),
        patch.object(run_assistant, "voicing_and_printing_answer") as answer,
    ):
        command.doing_task(spoken_text)

    answer.assert_called_once_with(
        "Відкриті папки у Провіднику:\n"
        "1. Завантаження — C:\\Users\\test\\Downloads\n"
        "2. Документи — C:\\Users\\test\\Documents\n"
        "Що зробити з відкритими вкладками? Назвіть номер вкладки, "
        "яку потрібно закрити, або скажіть, що залишити все як є."
    )


@pytest.mark.parametrize(
    "spoken_text",
    [
        "Покажи відкриті вікна",
        "Показати список відкритих вікон у Провіднику",
        "Покажи список наявних вікон",
        "Покажи всі відкриті вікна",
        "Які вікна зараз відкриті",
    ],
)
def test_open_explorer_windows_command_lists_window_tabs(spoken_text):
    windows = [
        ExplorerWindow(
            100,
            (
                ExplorerTab(r"C:\Users\test\Videos", "Videos", 100, 0),
                ExplorerTab(r"C:\Users\test\Documents", "Documents", 100, 1),
            ),
        ),
        ExplorerWindow(
            200,
            (ExplorerTab("shell:Home", "Главная", 200, 0),),
        ),
    ]
    command = make_command()
    with (
        patch.object(
            run_assistant, "get_open_explorer_windows", return_value=windows
        ) as get_windows,
        patch.object(run_assistant, "voicing_and_printing_answer") as answer,
    ):
        command.doing_task(spoken_text)

    get_windows.assert_called_once_with()
    answer.assert_called_once_with(
        "Відкриті вікна Провідника:\n"
        "1. Videos — C:\\Users\\test\\Videos, Documents — C:\\Users\\test\\Documents\n"
        "2. Главная\n"
        "Назвіть номер вікна, яке закрити, або скажіть «закрити всі»."
    )
    assert command.pending_explorer_windows == windows


def test_close_selected_explorer_window_from_list():
    windows = [
        ExplorerWindow(100, (ExplorerTab(r"C:\Users\test\Videos", "Videos", 100, 0),)),
        ExplorerWindow(
            200,
            (ExplorerTab(r"C:\Users\test\Documents", "Documents", 200, 0),),
        ),
    ]
    command = make_command()
    with (
        patch.object(run_assistant, "get_open_explorer_windows", return_value=windows),
        patch.object(run_assistant, "close_explorer_window", return_value=True) as close_window,
        patch.object(run_assistant, "voicing_and_printing_answer") as answer,
    ):
        command.doing_task("покажи відкриті вікна")
        command.doing_task("закрий вікно 2")

    close_window.assert_called_once_with(200)
    assert command.pending_explorer_windows is None
    assert answer.call_args.args[0] == "Закрила вибране вікно Провідника."


def test_close_all_explorer_windows_from_list():
    windows = [
        ExplorerWindow(100, (ExplorerTab(r"C:\Users\test\Videos", "Videos", 100, 0),))
    ]
    command = make_command()
    with (
        patch.object(run_assistant, "get_open_explorer_windows", return_value=windows),
        patch.object(run_assistant, "close_explorer_windows", return_value=1) as close_all,
        patch.object(run_assistant, "voicing_and_printing_answer") as answer,
    ):
        command.doing_task("покажи відкриті вікна")
        command.doing_task("закрити всі")

    close_all.assert_called_once_with()
    assert command.pending_explorer_windows is None
    assert answer.call_args.args[0] == "Закрила вікна Провідника. Закрито вікон: 1."


def test_other_command_clears_pending_explorer_window_selection():
    windows = [
        ExplorerWindow(100, (ExplorerTab(r"C:\Users\test\Videos", "Videos", 100, 0),))
    ]
    command = make_command()
    with (
        patch.object(run_assistant, "get_open_explorer_windows", return_value=windows),
        patch.object(run_assistant, "close_explorer_window") as close_window,
        patch.object(run_assistant, "voicing_and_printing_answer") as answer,
    ):
        command.doing_task("покажи відкриті вікна")
        command.doing_task("привіт")

    close_window.assert_not_called()
    assert command.pending_explorer_windows is None
    assert answer.call_args.args[0] == "Привіт, рада тебе бачити!"


def test_open_explorer_tabs_command_hides_virtual_namespace_guid():
    command = make_command()
    home_tab = ExplorerTab(
        "::{F874310E-B6B7-47DC-BC84-B9E6B38F5903}",
        "Главная",
        100,
        0,
    )
    with (
        patch.object(run_assistant, "get_open_explorer_tabs", return_value=[home_tab]),
        patch.object(run_assistant, "voicing_and_printing_answer") as answer,
    ):
        command.doing_task("покажи відкриті папки")

    answer.assert_called_once_with(
        "Відкриті папки у Провіднику:\n"
        "1. Главная\n"
        "Що зробити з відкритими вкладками? Назвіть номер вкладки, "
        "яку потрібно закрити, або скажіть, що залишити все як є."
    )


def test_close_folder_by_number_from_open_folders_list():
    tabs = [
        ExplorerTab(r"C:\Users\test\Videos", "Videos", 100, 0),
        ExplorerTab("shell:Home", "Главная", 100, 1),
    ]
    command = make_command()
    with (
        patch.object(run_assistant, "get_open_explorer_tabs", return_value=tabs),
        patch.object(run_assistant, "close_explorer_tab", return_value=True) as close_tab,
        patch.object(run_assistant, "voicing_and_printing_answer") as answer,
    ):
        command.doing_task("покажи відкриті папки")
        command.doing_task("закрити папку 2")

    close_tab.assert_called_once_with(tabs[1])
    assert command.pending_explorer_tabs is None
    assert answer.call_count == 2
    assert answer.call_args.args[0] == "Закрила папку Главная."


def test_confirming_close_from_list_prompts_for_number_then_closes_tab():
    tabs = [
        ExplorerTab(r"C:\Users\test\Videos", "Videos", 100, 0),
        ExplorerTab("shell:Home", "Главная", 100, 1),
    ]
    command = make_command()
    with (
        patch.object(run_assistant, "get_open_explorer_tabs", return_value=tabs),
        patch.object(run_assistant, "close_explorer_tab", return_value=True) as close_tab,
        patch.object(run_assistant, "voicing_and_printing_answer") as answer,
        patch.object(
            command,
            "analyze_response",
            return_value=ResponseAnalysis(ResponseCategory.CONFIRMATION, 1.0),
        ),
    ):
        command.doing_task("показати відкриті папки")
        command.doing_task("Можеш це зробити.")
        assert command.pending_explorer_tabs == tabs
        assert command.pending_explorer_tabs_awaiting_confirmation is False
        command.doing_task("2")

    close_tab.assert_called_once_with(tabs[1])
    assert answer.call_args.args[0] == "Закрила папку Главная."
    assert command.pending_explorer_tabs is None


def test_declining_close_from_list_clears_follow_up_state():
    command = make_command()
    with (
        patch.object(
            run_assistant,
            "get_open_explorer_tabs",
            return_value=[ExplorerTab(r"C:\Users\test\Videos", "Videos", 100, 0)],
        ),
        patch.object(run_assistant, "voicing_and_printing_answer") as answer,
        patch.object(
            command,
            "analyze_response",
            return_value=ResponseAnalysis(ResponseCategory.REJECTION, 1.0),
        ),
    ):
        command.doing_task("відкриті папки")
        command.doing_task("Залиш все як є.")

    assert command.pending_explorer_tabs is None
    assert answer.call_args.args[0] == "Залишаю вкладки відкритими."


def test_ambiguous_close_reply_is_clarified_and_list_stays_pending():
    command = make_command()
    tabs = [ExplorerTab(r"C:\Users\test\Videos", "Videos", 100, 0)]
    with (
        patch.object(run_assistant, "get_open_explorer_tabs", return_value=tabs),
        patch.object(run_assistant, "voicing_and_printing_answer") as answer,
        patch.object(
            command,
            "analyze_response",
            return_value=ResponseAnalysis(ResponseCategory.UNKNOWN, 0.2),
        ),
    ):
        command.doing_task("відкриті папки")
        command.doing_task("Може бути")

    assert command.pending_explorer_tabs == tabs
    assert command.pending_explorer_tabs_awaiting_confirmation is True
    assert answer.call_args.args[0] == (
        "Не зовсім зрозуміла. Назвіть номер вкладки, яку закрити, "
        "або скажіть, що залишити все як є."
    )


def test_next_unrelated_command_cancels_close_prompt_and_runs():
    command = make_command()
    with (
        patch.object(
            run_assistant,
            "get_open_explorer_tabs",
            return_value=[ExplorerTab(r"C:\Users\test\Videos", "Videos", 100, 0)],
        ),
        patch.object(run_assistant, "voicing_and_printing_answer") as answer,
    ):
        command.doing_task("відкриті папки")
        command.doing_task("привіт")

    assert command.pending_explorer_tabs is None
    assert answer.call_count == 2
    assert answer.call_args.args[0] == "Привіт, рада тебе бачити!"


def test_close_folder_number_out_of_range_keeps_list_available():
    tabs = [ExplorerTab(r"C:\Users\test\Videos", "Videos", 100, 0)]
    command = make_command()
    with (
        patch.object(run_assistant, "get_open_explorer_tabs", return_value=tabs),
        patch.object(run_assistant, "close_explorer_tab") as close_tab,
        patch.object(run_assistant, "voicing_and_printing_answer") as answer,
    ):
        command.doing_task("відкриті папки")
        command.doing_task("закрий папку 2")

    close_tab.assert_not_called()
    assert command.pending_explorer_tabs == tabs
    assert answer.call_args.args[0] == "Вкажіть номер від 1 до 1."


def test_open_explorer_tabs_command_interrupts_pending_file_selection():
    command = make_command()
    command.pending_file = {
        "awaiting_selection": True,
        "targets": [
            r"C:\Users\test\Videos\third_party",
            r"C:\Users\test\Videos\Videos",
        ],
    }

    with (
        patch.object(run_assistant, "get_open_explorer_tabs", return_value=[]) as get_tabs,
        patch.object(run_assistant, "voicing_and_printing_answer") as answer,
        patch.object(command, "handle_file_selection") as select_file,
    ):
        command.doing_task("покажи відкриті папки")

    get_tabs.assert_called_once_with()
    select_file.assert_not_called()
    answer.assert_called_once_with("У Провіднику немає відкритих папок.")
    assert command.pending_file is not None
    assert command.pending_file["awaiting_selection"] is True


def test_open_explorer_tabs_command_reports_empty_list():
    command = make_command()
    with (
        patch.object(run_assistant, "get_open_explorer_tabs", return_value=[]),
        patch.object(run_assistant, "voicing_and_printing_answer") as answer,
    ):
        command.doing_task("Які папки відкриті?")

    answer.assert_called_once_with("У Провіднику немає відкритих папок.")


def test_open_explorer_tabs_command_reports_read_error():
    command = make_command()
    with (
        patch.object(
            run_assistant,
            "get_open_explorer_tabs",
            side_effect=RuntimeError("UI Automation error"),
        ),
        patch.object(run_assistant, "voicing_and_printing_answer") as answer,
        patch.object(run_assistant.logger, "warning") as warning,
        patch.object(command.stdout, "write") as write,
    ):
        command.doing_task("Покажи відкриті папки")

    warning.assert_called_once_with("Reading Explorer tabs failed: %s", "RuntimeError")
    write.assert_not_called()
    answer.assert_called_once_with(
        "Не вдалося отримати список відкритих папок у Провіднику."
    )


def test_navigate_explorer_back_calls_com_go_back():
    with (
        patch("utils.file_explorer.platform.system", return_value="Windows"),
        patch("utils.file_explorer.subprocess.run") as run,
    ):
        run.return_value.returncode = 0
        run.return_value.stdout = "navigated-back\n"
        run.return_value.stderr = ""

        assert navigate_explorer_back() is True

    script = run.call_args.args[0][-1]
    assert "$window.GoBack()" in script
    assert "SetForegroundWindow($targetRoot)" not in script
    assert "Start-Sleep" not in script
    assert "SendBackShortcut" not in script
    assert "public static class AssistantExplorerWindow" in script
    assert "public static class AssistantExplorerBack" not in script
    assert "navigated-back" in script


def test_navigate_explorer_back_returns_false_without_explorer_window():
    with (
        patch("utils.file_explorer.platform.system", return_value="Windows"),
        patch("utils.file_explorer.subprocess.run") as run,
    ):
        run.return_value.returncode = 0
        run.return_value.stdout = "no-window\n"
        run.return_value.stderr = ""

        assert navigate_explorer_back() is False


def test_navigate_explorer_to_uses_shell_navigation_on_active_window():
    completed = Mock(returncode=0, stdout="navigated\n", stderr="")
    with (
        patch("utils.file_explorer.platform.system", return_value="Windows"),
        patch("utils.file_explorer.subprocess.run", return_value=completed) as run,
    ):
        assert navigate_explorer_to(r"C:\Users\test\Telegram Tech") is True

    assert run.call_args.kwargs["env"]["ASSISTANT_EXPLORER_TARGET"] == os.path.abspath(
        r"C:\Users\test\Telegram Tech"
    )
    script = run.call_args.args[0][-1]
    assert "SetForegroundWindow" in script
    assert "$window.Navigate($target)" in script
    assert "[string]::IsNullOrWhiteSpace($target)" in script
    assert "$fallbackToFirst = $true" in script
    assert "IsIconic($targetRoot)" in script
    assert "SW_RESTORE" in script
    assert "ReleaseComObject($shellWindow)" in script
    assert "ReleaseComObject($shellWindows)" in script


def test_navigate_explorer_to_returns_false_without_explorer_window():
    completed = Mock(returncode=0, stdout="no-window\n", stderr="")
    with (
        patch("utils.file_explorer.platform.system", return_value="Windows"),
        patch("utils.file_explorer.subprocess.run", return_value=completed),
    ):
        assert navigate_explorer_to(r"C:\Users\test\Telegram Tech") is False


def test_find_open_explorer_folders_matches_localized_downloads_alias():
    tab = ExplorerTab(
        r"C:\Users\test\Downloads",
        "Загрузки",
        100,
        0,
    )
    with (
        patch("utils.file_explorer.windows.get_open_explorer_tabs", return_value=[tab]),
    ):
        assert find_open_explorer_folders("завантаження") == [tab]


def test_find_open_explorer_folders_returns_all_matching_tabs():
    tabs = [
        ExplorerTab(r"C:\Users\test\Downloads", "Загрузки", 100, 0),
        ExplorerTab(r"C:\Users\test\Downloads", "Загрузки", 100, 1),
        ExplorerTab(r"C:\Users\test\Documents", "Документы", 200, 0),
    ]
    with patch("utils.file_explorer.windows.get_open_explorer_tabs", return_value=tabs):
        assert find_open_explorer_folders("Downloads") == tabs[:2]


def test_get_open_explorer_tabs_reads_paths_and_tab_indices_from_shell():
    output = (
        '[{"Path":"C:\\\\Users\\\\test\\\\Downloads",'
        '"Name":"Загрузки","Hwnd":100,"TabIndex":0}]'
    )
    with patch(
        "utils.file_explorer.windows._run_explorer_script",
        return_value=output,
    ) as run_script:
        assert get_open_explorer_tabs() == [
            ExplorerTab(r"C:\Users\test\Downloads", "Загрузки", 100, 0)
        ]

    assert "UIAutomationClient" in run_script.call_args.args[0]
    assert "TabItem" in run_script.call_args.args[0]
    script = run_script.call_args.args[0]
    assert "$window.Document" in script
    assert "if ($document)" in script
    assert "$path = \"shell:$virtualName\"" in script
    assert "LocationURL" in script
    assert "$usedComIndexes.ContainsKey($_.Index)" in script
    assert "$group.Group[$index]" not in script
    assert "кільком різним шляхам" in script
    assert 'Path = "shell:$tabName"' in script
    assert "if ($document)" in script
    assert "foreach ($window in $allWindows)" in script


def test_explorer_powershell_runner_uses_utf8_for_unicode_output():
    from utils.file_explorer.windows import _run_explorer_script

    completed = Mock(
        returncode=0,
        stdout="Відео",
        stderr="",
    )
    with (
        patch("utils.file_explorer.platform.system", return_value="Windows"),
        patch("utils.file_explorer.subprocess.run", return_value=completed) as run,
    ):
        assert _run_explorer_script("Write-Output 'Відео'") == "Відео"

    assert run.call_args.kwargs["encoding"] == "utf-8"
    assert run.call_args.kwargs["errors"] == "replace"
    assert "[Console]::OutputEncoding" in run.call_args.args[0][-1]


def test_close_explorer_tab_invokes_tab_close_button_when_available():
    tab = ExplorerTab(r"C:\Users\test\Downloads", "Загрузки", 100, 1)
    completed = Mock(returncode=0, stdout="close-invoked\n", stderr="")
    with patch(
        "utils.file_explorer.subprocess.run",
        return_value=completed,
    ) as run:
        assert close_explorer_tab(tab) is True

    assert run.call_args.kwargs["env"]["ASSISTANT_EXPLORER_HWND"] == "100"
    assert run.call_args.kwargs["env"]["ASSISTANT_EXPLORER_TAB_INDEX"] == "1"
    script = run.call_args.args[0][-1]
    assert "'CloseButton'" in script
    assert "InvokePattern" in script
    assert "$invokePattern.Invoke()" in script
    assert script.index("$invokePattern.Invoke()") < script.index(
        "$selectionPattern.Select()"
    )
    assert "SendWait('^{w}')" in script


def test_close_explorer_tab_falls_back_to_ctrl_w():
    tab = ExplorerTab(r"C:\Users\test\Downloads", "Загрузки", 100, 1)
    completed = Mock(returncode=0, stdout="close-sent\n", stderr="")
    with patch(
        "utils.file_explorer.subprocess.run",
        return_value=completed,
    ):
        assert close_explorer_tab(tab) is True


def test_close_folder_command_does_not_search_installed_apps():
    command = make_command()

    with (
        patch.object(
            run_assistant,
            "find_open_explorer_folders",
            return_value=[
                ExplorerTab(r"C:\Users\test\C Sharp", "C Sharp", 100, 0)
            ],
        ),
        patch.object(
            run_assistant, "close_explorer_tab", return_value=True
        ) as close_folder,
        patch.object(run_assistant, "get_known_apps") as get_apps,
        patch.object(run_assistant, "voicing_and_printing_answer"),
    ):
        command.doing_task("закрити папку C Sharp")

    close_folder.assert_called_once_with(
        ExplorerTab(r"C:\Users\test\C Sharp", "C Sharp", 100, 0)
    )
    get_apps.assert_not_called()


def test_close_folder_prompts_for_selection_when_multiple_tabs_match():
    tabs = [
        ExplorerTab(r"C:\Users\test\Downloads", "Загрузки", 100, 0),
        ExplorerTab(r"C:\Users\test\Downloads", "Загрузки", 100, 1),
    ]
    command = make_command()
    with (
        patch.object(run_assistant, "find_open_explorer_folders", return_value=tabs),
        patch.object(run_assistant, "close_explorer_tab") as close_tab,
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
        patch.object(command.stdout, "write") as write,
    ):
        command.doing_task("закрити папку завантаження")

    close_tab.assert_not_called()
    assert command.pending_file is not None
    assert command.pending_file["awaiting_explorer_close_selection"] is True
    assert command.pending_file["targets"] == tabs
    assert "1. Загрузки" in write.call_args.args[0]
    assert "2. Загрузки" in write.call_args.args[0]
    assert "Вкажіть номер" in speak.call_args.args[0]


def test_close_folder_selection_closes_only_selected_tab():
    tabs = [
        ExplorerTab(r"C:\Users\test\Downloads", "Загрузки", 100, 0),
        ExplorerTab(r"C:\Users\test\Downloads", "Загрузки", 100, 1),
    ]
    command = make_command()
    command.pending_file = {
        "awaiting_explorer_close_selection": True,
        "targets": tabs,
    }
    with (
        patch.object(
            run_assistant, "close_explorer_tab", return_value=True
        ) as close_tab,
        patch.object(run_assistant, "voicing_and_printing_answer"),
    ):
        command.doing_task("варіант 2")

    close_tab.assert_called_once_with(tabs[1])
    assert command.pending_file is None


def test_forward_navigation_lists_small_number_of_subfolders(tmp_path):
    folders = [
        str(tmp_path / f"Folder {index}")
        for index in range(1, 8)
    ]
    command = make_command()

    with (
        patch.object(run_assistant, "get_active_explorer_subfolders", return_value=folders),
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
        patch.object(command.stdout, "write") as write,
    ):
        command.navigate_explorer_forward()

    assert write.call_args.args[0] == "Підпапки: " + "; ".join(
        f"{index}. Folder {index}" for index in range(1, 8)
    )
    assert "Вкажіть назву папки або номер" in speak.call_args.args[0]
    assert command.pending_file is not None
    assert command.pending_file["awaiting_explorer_folder_name"] is True


def test_forward_navigation_with_unmatched_name_offers_screen_list_and_retry(
    tmp_path,
):
    folders = [
        str(tmp_path / "AI"),
        str(tmp_path / "Django"),
        str(tmp_path / "Lesson_tasks"),
        str(tmp_path / "Projects"),
    ]
    command = make_command()
    with (
        patch.object(
            run_assistant,
            "get_active_explorer_subfolders",
            return_value=folders,
        ),
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
        patch.object(command.stdout, "write") as write,
        patch.object(run_assistant, "navigate_explorer_to") as navigate,
    ):
        command.doing_task("вперед John")

    assert write.call_args.args[0] == (
        "Підпапки: 1. AI; 2. Django; 3. Lesson_tasks; 4. Projects"
    )
    assert "Список показано на екран" in speak.call_args.args[0]
    assert "Вкажіть номер" in speak.call_args.args[0]
    assert "уточніть назву" in speak.call_args.args[0]
    assert "AI; Django" not in speak.call_args.args[0]
    assert command.pending_file is not None
    assert command.pending_file["awaiting_explorer_folder_name"] is True
    navigate.assert_not_called()


def test_forward_navigation_prompts_for_name_when_more_than_seven_folders(tmp_path):
    folders = [str(tmp_path / f"Folder {index}") for index in range(1, 10)]
    command = make_command()

    with (
        patch.object(run_assistant, "get_active_explorer_subfolders", return_value=folders),
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
        patch.object(command.stdout, "write") as write,
    ):
        command.navigate_explorer_forward()

    write.assert_not_called()
    assert "більше семи" in speak.call_args.args[0]
    assert command.pending_file is not None
    assert command.pending_file["targets"] == folders


def test_forward_navigation_opens_requested_child_folder_by_name(tmp_path):
    child = tmp_path / "Telegram Desktop"
    command = make_command()
    command.pending_file = {
        "awaiting_explorer_folder_name": True,
        "targets": [str(child)],
    }

    with (
        patch.object(run_assistant, "navigate_explorer_to", return_value=True) as navigate,
        patch.object(run_assistant, "voicing_and_printing_answer"),
    ):
        command.doing_task("Telegram")

    navigate.assert_called_once_with(str(child))
    assert command.pending_file is None


def test_explorer_folder_name_matching_ignores_extra_unrecognized_words(tmp_path):
    telegram = str(tmp_path / "Telegram Desktop")
    downloads = str(tmp_path / "Downloads")

    assert Command._match_explorer_folder_name(
        "вперед Telegram тексто",
        [telegram, downloads],
    ) == telegram


def test_explorer_folder_name_can_be_selected_by_number(tmp_path):
    folders = [
        str(tmp_path / "AI"),
        str(tmp_path / "Django"),
        str(tmp_path / "Lesson_tasks"),
        str(tmp_path / "Projects"),
    ]
    command = make_command()
    command.pending_file = {
        "awaiting_explorer_folder_name": True,
        "targets": folders,
    }

    with (
        patch.object(run_assistant, "navigate_explorer_to", return_value=True) as navigate,
        patch.object(run_assistant, "voicing_and_printing_answer"),
    ):
        command.doing_task("варіант 4")

    navigate.assert_called_once_with(folders[3])
    assert command.pending_file is None


def test_explorer_folder_name_matching_supports_ukrainian_pronunciation_of_english(
    tmp_path,
):
    frontend = str(tmp_path / "frontend")

    assert Command._match_explorer_folder_name(
        "фронтенд",
        [frontend],
    ) == frontend


def test_explorer_folder_name_matching_returns_none_for_ambiguous_name(tmp_path):
    telegram_desktop = str(tmp_path / "Telegram Desktop")
    telegram_tech = str(tmp_path / "Telegram Tech")

    assert Command._match_explorer_folder_name(
        "Telegram",
        [telegram_desktop, telegram_tech],
    ) is None


def test_unmatched_explorer_folder_name_does_not_repeat_prompt(tmp_path):
    command = make_command()
    command.pending_file = {
        "awaiting_explorer_folder_name": True,
        "targets": [str(tmp_path / "Telegram Desktop")],
    }

    with (
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
        patch.object(run_assistant, "navigate_explorer_to") as navigate,
    ):
        command.doing_task("скажіть")
        command.doing_task("random garbled speech")

    speak.assert_not_called()
    navigate.assert_not_called()
    assert command.pending_file is not None


def test_forward_command_uses_trailing_folder_name_without_selection_prompt(tmp_path):
    frontend = str(tmp_path / "frontend")
    command = make_command()

    with (
        patch.object(
            run_assistant,
            "get_active_explorer_subfolders",
            return_value=[frontend],
        ),
        patch.object(run_assistant, "navigate_explorer_to", return_value=True) as navigate,
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
        patch.object(command.stdout, "write") as write,
    ):
        command.doing_task("вперед фронтенд")

    navigate.assert_called_once_with(frontend)
    assert command.pending_file is None
    write.assert_not_called()
    speak.assert_called_once()
    assert "Перейшла до папки frontend" in speak.call_args.args[0]


@pytest.mark.parametrize(
    ("spoken_text", "requested_name"),
    [
        ("далі", ""),
        ("далі фронтенд", "фронтенд"),
        ("далі по папках", ""),
        ("вперед фронтенд", "фронтенд"),
    ],
)
def test_forward_navigation_accepts_dali_synonym(
    spoken_text,
    requested_name,
):
    command = make_command()
    with (
        patch.object(run_assistant, "get_active_explorer_subfolders", return_value=[]),
        patch.object(command, "navigate_explorer_forward") as navigate,
        patch.object(run_assistant, "voicing_and_printing_answer"),
    ):
        command.doing_task(spoken_text)

    navigate.assert_called_once_with(requested_name=requested_name)


def test_unrecognized_audio_is_silent_while_waiting_for_explorer_folder(tmp_path):
    command = make_command()
    command.stdout = Mock()
    command.pending_file = {
        "awaiting_explorer_folder_name": True,
        "targets": [str(tmp_path / "Telegram Desktop")],
    }

    command.handle_unrecognized_audio()

    command.stdout.write.assert_not_called()


def test_back_navigation_cancels_pending_file_selection():
    command = make_command()
    command.pending_file = {
        "awaiting_selection": True,
        "targets": [r"C:\Users\test\Downloads\Telegram Desktop"],
    }

    with patch.object(command, "navigate_explorer_back") as navigate_back:
        command.doing_task("назад")

    navigate_back.assert_called_once_with()
    assert command.pending_file is None


def test_missing_file_target_can_be_provided_in_follow_up(tmp_path):
    target = tmp_path / "звіт.docx"
    target.touch()
    command = make_command()

    with (
        patch.object(run_assistant, "open_target") as open_target,
        patch.object(run_assistant, "voicing_and_printing_answer"),
    ):
        command.doing_task("відкрий файл")
        command.doing_task(str(target))

    open_target.assert_called_once_with(str(target))


def test_cancel_while_waiting_for_file_selection_does_not_open_target(tmp_path):
    target = tmp_path / "звіт.docx"
    target.touch()
    command = make_command()
    command.pending_file = {
        "awaiting_selection": True,
        "targets": [str(target)],
    }

    with (
        patch.object(run_assistant, "open_target") as open_target,
        patch.object(run_assistant, "voicing_and_printing_answer"),
    ):
        command.doing_task("скасуй")

    assert command.pending_file is None
    open_target.assert_not_called()


def test_similar_file_suggestions_wait_for_numbered_selection(tmp_path):
    first = tmp_path / "теорія.docx"
    second = tmp_path / "теорія-конспект.docx"
    first.touch()
    second.touch()
    command = make_command()

    with (
        patch.object(run_assistant, "find_file_targets", return_value=[]),
        patch.object(
            run_assistant,
            "find_similar_file_targets",
            return_value=[str(first), str(second)],
        ),
        patch.object(run_assistant, "open_target") as open_target,
        patch.object(run_assistant, "voicing_and_printing_answer") as speak,
    ):
        command.stdout = Mock()
        command.handle_file_open("file", "теорія")

        pending_file = command.pending_file
        assert pending_file is not None
        assert pending_file["targets"] == [str(first), str(second)]
        assert "Варіанти файлів і папок:" in command.stdout.write.call_args.args[0]
        spoken_message = speak.call_args.args[0]
        assert "теорія.docx" not in spoken_message
        assert "Варіанти:" not in spoken_message
        assert "скасувати" in spoken_message
        open_target.assert_not_called()

        command.doing_task("другий")
        assert command.pending_file is not None
        assert command.pending_file["awaiting_selection_confirmation"] is True
        open_target.assert_not_called()

        command.analyze_response = Mock(
            return_value=ResponseAnalysis(
                ResponseCategory.CONFIRMATION,
                1.0,
                source=ResponseSource.PATTERN,
            )
        )
        command.doing_task("так")

    open_target.assert_called_once_with(str(second))
    assert command.pending_file is None
