import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Assistant.settings")

import django

django.setup()

import pytest
from django.core.management import call_command
from django.db import connection

from core.models import AppCommand
from utils.match_app import (
    get_app_open_counts,
    increment_open_count,
    register_found_app,
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
    increment_open_count(stale)  # `stale.open_count` is still 0 in memory

    assert AppCommand.objects.get(pk=stale.pk).open_count == 2


def test_get_app_open_counts_returns_frequency_for_requested_apps(memory_db):
    steam = register_found_app(name="Steam", path="C:\\Apps\\steam.exe")
    other = register_found_app(name="Other", path="C:\\Apps\\other.exe")
    increment_open_count(steam)
    increment_open_count(steam)
    increment_open_count(other)

    assert get_app_open_counts(["Steam"]) == {"Steam": 2}
