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
    close_explorer_tab,
    close_explorer_windows,
    find_open_explorer_folders,
    get_open_explorer_tabs,
    find_file_targets,
    find_similar_file_targets,
    get_active_explorer_path,
    get_active_explorer_subfolders,
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
        ("Відкрий провідник", ("folder", "провідник", False)),
        ("Відкрий файл", ("file", "", False)),
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


@pytest.mark.parametrize(
    "spoken_folder",
    ["документи", "документів", "документа", "документу", "документах"],
)
def test_document_folder_alias_accepts_inflected_forms(monkeypatch, spoken_folder):
    documents_path = r"C:\Users\test\Documents"
    resolve_folder = Mock(return_value=documents_path)
    monkeypatch.setattr("utils.file_explorer._standard_folder_path", resolve_folder)

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
        "utils.file_explorer._standard_folder_path",
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
    monkeypatch.setattr("utils.file_explorer._standard_folder_path", lambda _name: None)

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


def test_open_explorer_voice_command_launches_file_manager():
    command = make_command()

    with (
        patch.object(run_assistant, "open_target") as open_target,
        patch.object(run_assistant, "voicing_and_printing_answer"),
    ):
        command.doing_task("відкрий Провідник")

    open_target.assert_called_once_with("explorer")


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
    assert "SendShortcut(0x54)" in script
    assert "SendShortcut(0x4C)" in script
    assert "SendShortcut(0x41)" in script
    assert "TypeText($env:ASSISTANT_EXPLORER_TARGET)" in script
    assert "Navigate2" not in script
    popen.assert_not_called()


def test_music_alias_resolves_to_music_folder_not_home(monkeypatch, tmp_path):
    home = tmp_path / "user"
    music = home / "Music"
    music.mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("OneDrive", "")
    monkeypatch.setattr("utils.file_explorer.os.path.expanduser", lambda _path: str(home))

    assert find_file_targets("музика", expected_kind="folder") == [str(music)]


def test_folder_opens_in_new_explorer_window_when_requested(tmp_path):
    folder = tmp_path / "Документи"
    folder.mkdir()

    with (
        patch("utils.file_explorer.platform.system", return_value="Windows"),
        patch("utils.file_explorer.subprocess.Popen") as popen,
        patch("utils.file_explorer.subprocess.run") as run,
    ):
        open_target(str(folder), new_window=True)

    popen.assert_called_once_with(["explorer.exe", "/n", str(folder)])
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


def test_close_explorer_windows_only_closes_explorer_windows():
    completed = Mock(returncode=0, stdout="2\n", stderr="")
    with (
        patch("utils.file_explorer.platform.system", return_value="Windows"),
        patch("utils.file_explorer.subprocess.run", return_value=completed) as run,
    ):
        assert close_explorer_windows() == 2

    assert "explorer.exe" in run.call_args.args[0][-1]
    assert "window.Quit()" in run.call_args.args[0][-1]
    assert "Stop-Process" not in run.call_args.args[0][-1]


def test_active_explorer_path_is_read_from_selected_window():
    with (
        patch(
            "utils.file_explorer._run_explorer_script",
            return_value=r"C:\Users\test\Documents",
        ) as run_script,
        patch("utils.file_explorer.platform.system", return_value="Windows"),
    ):
        assert get_active_explorer_path() == os.path.normpath(
            r"C:\Users\test\Documents"
        )

    script = run_script.call_args.args[0]
    assert "matchingWindows.Count -gt 1" in script
    assert "AutomationIdProperty" in script
    assert "'TabView'" in script
    assert "SelectionItemPattern" in script
    assert "$matchingWindows[$selectedTabIndex]" in script


def test_active_explorer_subfolders_are_sorted(tmp_path):
    (tmp_path / "Zulu").mkdir()
    (tmp_path / "Alpha").mkdir()
    (tmp_path / "not-a-folder.txt").touch()

    with patch(
        "utils.file_explorer.get_active_explorer_path",
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
        "utils.file_explorer.get_active_explorer_path",
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
            "utils.file_explorer.get_active_explorer_path",
            return_value=namespace_path,
        ),
        patch("utils.file_explorer.os.path.isdir", return_value=False),
        patch(
            "utils.file_explorer._run_explorer_script",
            return_value='["D:\\\\", "C:\\\\"]',
        ) as run_script,
    ):
        folders = get_active_explorer_subfolders()

    assert folders == ["C:\\", "D:\\"]
    script = run_script.call_args.args[0]
    assert "$window.Document.Folder.Items()" in script
    assert "$_.IsFolder" in script


def test_active_explorer_virtual_folder_without_subfolders_returns_empty_list():
    with (
        patch(
            "utils.file_explorer.get_active_explorer_path",
            return_value="::{F874310E-B6B7-47DC-BC84-B9E6B38F5903}",
        ),
        patch("utils.file_explorer.os.path.isdir", return_value=False),
        patch("utils.file_explorer._run_explorer_script", return_value="[]"),
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


def test_navigate_explorer_back_calls_shell_back():
    with (
        patch("utils.file_explorer.platform.system", return_value="Windows"),
        patch("utils.file_explorer.subprocess.run") as run,
    ):
        run.return_value.returncode = 0
        run.return_value.stdout = "shortcut-sent\n"
        run.return_value.stderr = ""

        assert navigate_explorer_back() is True

    script = run.call_args.args[0][-1]
    assert "SetForegroundWindow" in script
    assert "SendBackShortcut" in script
    assert "CreateKeyInput(0x12, 0)" in script
    assert "CreateKeyInput(0x25, 0)" in script
    assert "shortcut-sent" in script


def test_navigate_explorer_back_returns_false_without_explorer_window():
    with (
        patch("utils.file_explorer.platform.system", return_value="Windows"),
        patch("utils.file_explorer.subprocess.run") as run,
    ):
        run.return_value.returncode = 0
        run.return_value.stdout = "no-window\n"
        run.return_value.stderr = ""

        assert navigate_explorer_back() is False


def test_navigate_explorer_to_types_path_into_active_window():
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
    assert "NavigateTo($env:ASSISTANT_EXPLORER_TARGET)" in script
    assert "SendKey(0x4C, 0, 0)" in script
    assert "SendKey(0x0D, 0, 0)" in script


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
        patch("utils.file_explorer.get_open_explorer_tabs", return_value=[tab]),
    ):
        assert find_open_explorer_folders("завантаження") == [tab]


def test_find_open_explorer_folders_returns_all_matching_tabs():
    tabs = [
        ExplorerTab(r"C:\Users\test\Downloads", "Загрузки", 100, 0),
        ExplorerTab(r"C:\Users\test\Downloads", "Загрузки", 100, 1),
        ExplorerTab(r"C:\Users\test\Documents", "Документы", 200, 0),
    ]
    with patch("utils.file_explorer.get_open_explorer_tabs", return_value=tabs):
        assert find_open_explorer_folders("Downloads") == tabs[:2]


def test_get_open_explorer_tabs_reads_paths_and_tab_indices_from_shell():
    output = (
        '[{"Path":"C:\\\\Users\\\\test\\\\Downloads",'
        '"Name":"Загрузки","Hwnd":100,"TabIndex":0}]'
    )
    with patch(
        "utils.file_explorer._run_explorer_script",
        return_value=output,
    ) as run_script:
        assert get_open_explorer_tabs() == [
            ExplorerTab(r"C:\Users\test\Downloads", "Загрузки", 100, 0)
        ]

    assert "UIAutomationClient" in run_script.call_args.args[0]
    assert "TabItem" in run_script.call_args.args[0]


def test_close_explorer_tab_selects_one_tab_and_sends_ctrl_w():
    tab = ExplorerTab(r"C:\Users\test\Downloads", "Загрузки", 100, 1)
    completed = Mock(returncode=0, stdout="close-sent\n", stderr="")
    with patch(
        "utils.file_explorer.subprocess.run",
        return_value=completed,
    ) as run:
        assert close_explorer_tab(tab) is True

    assert run.call_args.kwargs["env"]["ASSISTANT_EXPLORER_HWND"] == "100"
    assert run.call_args.kwargs["env"]["ASSISTANT_EXPLORER_TAB_INDEX"] == "1"
    script = run.call_args.args[0][-1]
    assert "$selection.Select()" in script
    assert "SendWait('^{w}')" in script


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
    assert command.pending_file["awaiting_explorer_close_selection"] is True
    assert command.pending_file["targets"] == tabs
    assert "1. Загрузки" in write.call_args.args[0]
    assert "2. Загрузки" in write.call_args.args[0]
    assert "Назвіть номер" in speak.call_args.args[0]


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
        f"Folder {index}" for index in range(1, 8)
    )
    assert "Назвіть папку" in speak.call_args.args[0]
    assert command.pending_file["awaiting_explorer_folder_name"] is True


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
