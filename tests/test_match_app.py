import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Assistant.settings")

import django

django.setup()

from utils.match_app import find_best_match


def test_ignores_generic_program_word_and_selects_exact_app_name():
    apps = {
        "paste": "C:\\Apps\\paste.exe",
        "Steam": "C:\\Apps\\steam.exe",
    }

    assert find_best_match("програму Steam", apps) == (
        "Steam",
        "C:\\Apps\\steam.exe",
    )


def test_selects_similar_app_name_when_user_mispronounces_it():
    apps = {
        "paste": "C:\\Apps\\paste.exe",
        "Steam": "C:\\Apps\\steam.exe",
    }

    assert find_best_match("програму Steem", apps) == (
        "Steam",
        "C:\\Apps\\steam.exe",
    )


def test_returns_no_match_when_similar_names_are_ambiguous():
    apps = {
        "Steam": "C:\\Apps\\steam.exe",
        "Steem": "C:\\Apps\\steem.exe",
    }

    assert find_best_match("Ste", apps) == (None, None)


def test_returns_no_match_for_generic_word_without_app_name():
    apps = {
        "paste": "C:\\Apps\\paste.exe",
        "Steam": "C:\\Apps\\steam.exe",
    }

    assert find_best_match("програму", apps) == (None, None)


def test_cyrillic_app_name_prefers_standalone_app_over_internal_tool():
    apps = {
        "Cursor": "C:\\Apps\\Cursor.exe",
        "cursor-tunnel": "C:\\Apps\\Cursor\\resources\\app\\bin\\cursor-tunnel.exe",
    }

    assert find_best_match("курсор", apps) == (
        "Cursor",
        "C:\\Apps\\Cursor.exe",
    )
