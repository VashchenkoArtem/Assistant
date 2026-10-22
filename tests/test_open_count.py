import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Assistant.settings")

import django

django.setup()

import pytest
from django.core.management import call_command
from django.db import connection

from core.models import (
    AppCommand,
)
from utils.match_app import (
    get_app_open_counts,
    get_known_apps,
    increment_open_count,
    register_found_app,
    sync_installed_apps,
)


@pytest.fixture
def memory_db():
    """Real Django DB (in-memory sqlite) so the F() update is actually executed."""
    original = connection.settings_dict["NAME"]
    connection.close()
    connection.settings_dict["NAME"] = ":memory:"
    call_command("migrate", verbosity=0)
    try:
        yield
    finally:
        connection.close()
        connection.settings_dict["NAME"] = original


def test_register_found_app_creates_command_with_zero_opens(memory_db):
    command = register_found_app(name="Steam", path="C:\\Apps\\steam.exe")

    assert command.pk is not None
    assert command.open_count == 0


def test_register_found_app_returns_existing_command_without_touching_count(memory_db):
    first = register_found_app(name="Steam", path="C:\\Apps\\steam.exe")
    increment_open_count(first)

    again = register_found_app(name="Steam", path="C:\\Apps\\steam.exe")

    assert again.pk == first.pk
    assert AppCommand.objects.count() == 1
    assert AppCommand.objects.get(pk=first.pk).open_count == 1


def test_increment_open_count_counts_every_open_and_only_that_app(memory_db):
    steam = register_found_app(name="Steam", path="C:\\Apps\\steam.exe")
    other = register_found_app(name="Paste", path="C:\\Apps\\paste.exe")

    for _ in range(3):
        increment_open_count(steam)

    assert AppCommand.objects.get(pk=steam.pk).open_count == 3
    assert AppCommand.objects.get(pk=other.pk).open_count == 0


def test_increment_uses_db_value_not_stale_instance(memory_db):
    stale = register_found_app(name="Steam", path="C:\\Apps\\steam.exe")
    increment_open_count(stale)
    increment_open_count(stale)

    assert AppCommand.objects.get(pk=stale.pk).open_count == 2


def test_get_app_open_counts_returns_frequency_for_requested_apps(memory_db):
    steam = register_found_app(name="Steam", path="C:\\Apps\\steam.exe")
    other = register_found_app(name="Other", path="C:\\Apps\\other.exe")
    increment_open_count(steam)
    increment_open_count(steam)
    increment_open_count(other)

    assert get_app_open_counts(["Steam"]) == {"Steam": 2}


def test_sync_installed_apps_saves_every_discovered_app(memory_db):
    count = sync_installed_apps(
        {
            "Steam": "C:\\Apps\\steam.exe",
            "Spotify": "appx://Spotify!App",
        }
    )

    assert count == 2
    assert set(AppCommand.objects.values_list("name", flat=True)) == {
        "Steam",
        "Spotify",
    }


def test_sync_installed_apps_filters_technical_executables(memory_db):
    count = sync_installed_apps(
        {
            "Steam": "C:\\Apps\\steam.exe",
            "Uninstall": "C:\\Apps\\uninstall.exe",
            "Example": "C:\\Apps\\unins000.exe",
        }
    )

    assert count == 1
    assert list(AppCommand.objects.values_list("name", flat=True)) == ["Steam"]


def test_known_apps_hides_legacy_technical_executable_records(memory_db, monkeypatch):
    register_found_app(name="Steam", path="C:\\Apps\\steam.exe")
    register_found_app(name="Uninstall", path="C:\\Apps\\uninstall.exe")
    monkeypatch.setattr("utils.match_app.get_list_installed_apps", lambda: {})

    assert get_known_apps() == {"Steam": "C:\\Apps\\steam.exe"}


def test_sync_installed_apps_preserves_existing_open_counts(memory_db):
    steam = register_found_app(name="Steam", path="C:\\Apps\\steam.exe")
    increment_open_count(steam)

    sync_installed_apps({"Steam": "C:\\Apps\\steam.exe"})

    assert AppCommand.objects.get(name="Steam").open_count == 1
