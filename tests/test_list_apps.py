import json
import logging
import os
from subprocess import CompletedProcess, TimeoutExpired
from types import SimpleNamespace
from unittest.mock import patch

import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Assistant.settings")

import django

django.setup()

from utils.list_apps import _get_windows_store_apps, get_list_installed_apps
from utils.match_app import find_best_match, get_known_apps
from core.models import AppCommand


@pytest.fixture(autouse=True)
def clear_installed_apps_cache():
    get_list_installed_apps.cache_clear()
    yield
    get_list_installed_apps.cache_clear()


def test_installed_apps_are_cached_until_cache_is_cleared():
    with (
        patch("utils.list_apps.platform.system", return_value="Linux"),
        patch(
            "utils.list_apps.search_dirs_and_extentions",
            return_value=([], (".desktop",)),
        ) as search_dirs,
    ):
        assert get_list_installed_apps() == {}
        assert get_list_installed_apps() == {}

    search_dirs.assert_called_once_with()


def test_known_apps_do_not_mutate_cached_installed_apps():
    installed_apps = {"Spotify": "appx://Spotify!Spotify"}
    learned_app = SimpleNamespace(name="Example", path=r"C:\Apps\example.exe")

    with (
        patch("utils.match_app.get_list_installed_apps", return_value=installed_apps),
        patch.object(AppCommand.objects, "all", return_value=[learned_app]),
    ):
        known_apps = get_known_apps()

    assert known_apps == {
        "Spotify": "appx://Spotify!Spotify",
        "Example": r"C:\Apps\example.exe",
    }
    assert installed_apps == {"Spotify": "appx://Spotify!Spotify"}


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
    assert run.call_args.kwargs["timeout"] == 30
    assert run.call_args.kwargs["check"] is False


def test_store_app_timeout_falls_back_to_regular_app_scan(
    tmp_path,
    monkeypatch,
    caplog,
):
    executable = tmp_path / "Example.exe"
    executable.touch()
    get_list_installed_apps.cache_clear()
    monkeypatch.setattr("utils.list_apps.platform.system", lambda: "Windows")

    with (
        patch(
            "utils.list_apps.subprocess.run",
            side_effect=TimeoutExpired(["powershell"], timeout=30),
        ),
        patch(
            "utils.list_apps.search_dirs_and_extentions",
            return_value=([str(tmp_path)], (".exe", ".lnk")),
        ),
        caplog.at_level(logging.WARNING, logger="utils.list_apps"),
    ):
        try:
            apps = get_list_installed_apps()
        finally:
            get_list_installed_apps.cache_clear()

    assert apps == {"Example": str(executable)}
    assert "continuing without Store apps" in caplog.text


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


def test_technical_executables_are_not_discovered(tmp_path, monkeypatch):
    program_dir = tmp_path / "Programs" / "Example"
    program_dir.mkdir(parents=True)
    (program_dir / "Example.exe").touch()
    (program_dir / "unins000.exe").touch()
    (program_dir / "Uninstall.exe").touch()
    (program_dir / "Update.exe").touch()

    monkeypatch.setattr("utils.list_apps.platform.system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("PROGRAMFILES", "")
    monkeypatch.setenv("PROGRAMFILES(X86)", "")
    monkeypatch.setenv("APPDATA", "")
    monkeypatch.setenv("PROGRAMDATA", "")

    with patch("utils.list_apps._get_windows_store_apps", return_value={}):
        apps = get_list_installed_apps()

    assert apps == {"Example": str(program_dir / "Example.exe")}
