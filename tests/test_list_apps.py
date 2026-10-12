import json
import os
from subprocess import CompletedProcess
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Assistant.settings")

import django

django.setup()

from utils.list_apps import _get_windows_store_apps, get_list_installed_apps
from utils.match_app import find_best_match


def test_windows_store_apps_are_returned_with_launcher_id():
    entries = [
        {
            "Name": "Spotify",
            "AppID": "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify",
        }
    ]
    result = CompletedProcess(
        args=["powershell"],
        returncode=0,
        stdout=json.dumps(entries),
        stderr="",
    )

    with patch("utils.list_apps.subprocess.run", return_value=result) as run:
        apps = _get_windows_store_apps()

    assert apps == {
        "Spotify": (
            "appx://SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"
        )
    }
    assert run.call_args.kwargs["timeout"] == 15
    assert run.call_args.kwargs["check"] is False


def test_windows_store_app_lookup_reports_powershell_failure():
    result = CompletedProcess(
        args=["powershell"],
        returncode=1,
        stdout="",
        stderr="Access denied",
    )

    with patch("utils.list_apps.subprocess.run", return_value=result):
        try:
            _get_windows_store_apps()
        except RuntimeError as error:
            assert "Access denied" in str(error)
        else:
            raise AssertionError("Expected Windows Store app lookup to fail explicitly")


def test_store_apps_are_included_in_searchable_installed_apps():
    store_apps = {
        "Spotify": "appx://SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"
    }
    with (
        patch("utils.list_apps.platform.system", return_value="Windows"),
        patch("utils.list_apps._get_windows_store_apps", return_value=store_apps),
        patch(
            "utils.list_apps.search_dirs_and_extentions",
            return_value=([], (".exe", ".lnk")),
        ),
    ):
        apps = get_list_installed_apps()

    assert apps["Spotify"] == store_apps["Spotify"]
    assert find_best_match("Spotify", apps) == (
        "Spotify",
        store_apps["Spotify"],
    )


def test_user_local_programs_are_discovered_with_executable_extension(
    tmp_path, monkeypatch
):
    cursor_dir = tmp_path / "Programs" / "Cursor"
    cursor_dir.mkdir(parents=True)
    cursor_executable = cursor_dir / "Cursor.exe"
    cursor_executable.touch()

    monkeypatch.setattr("utils.list_apps.platform.system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("PROGRAMFILES", "")
    monkeypatch.setenv("PROGRAMFILES(X86)", "")
    monkeypatch.setenv("APPDATA", "")
    monkeypatch.setenv("PROGRAMDATA", "")

    with patch("utils.list_apps._get_windows_store_apps", return_value={}):
        apps = get_list_installed_apps()

    assert apps["Cursor"] == str(cursor_executable)
    assert find_best_match("курсор", apps) == ("Cursor", str(cursor_executable))
