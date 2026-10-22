import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Assistant.settings")

import django

django.setup()

import utils.match_app as match_app
from utils.match_app import (
    find_best_match,
    find_exact_match,
    find_similar_apps,
)


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


def test_similarity_takes_precedence_over_open_frequency(monkeypatch):
    apps = {
        "Steam": "C:\\Apps\\steam.exe",
        "Steam Tools": "C:\\Apps\\steam-tools.exe",
    }
    scores = {"steam": 0.9, "steam tools": 0.8}
    monkeypatch.setattr(
        match_app,
        "_similarity",
        lambda _query, name: scores[name],
    )

    assert find_best_match(
        "steam",
        apps,
        open_counts={"Steam": 1, "Steam Tools": 100},
    ) == ("Steam", "C:\\Apps\\steam.exe")


def test_open_frequency_breaks_equal_similarity_tie(monkeypatch):
    apps = {
        "Steam": "C:\\Apps\\steam.exe",
        "Steam Tools": "C:\\Apps\\steam-tools.exe",
    }
    monkeypatch.setattr(match_app, "_similarity", lambda _query, _name: 0.9)

    assert find_best_match(
        "steam",
        apps,
        open_counts={"Steam": 2, "Steam Tools": 12},
    ) == ("Steam Tools", "C:\\Apps\\steam-tools.exe")


def test_open_frequency_does_not_resolve_close_similarity_ambiguity(monkeypatch):
    apps = {
        "Steam": "C:\\Apps\\steam.exe",
        "Steam Tools": "C:\\Apps\\steam-tools.exe",
    }
    scores = {"steam": 0.9, "steam tools": 0.89}
    monkeypatch.setattr(
        match_app,
        "_similarity",
        lambda _query, name: scores[name],
    )

    assert find_best_match(
        "steam",
        apps,
        open_counts={"Steam": 0, "Steam Tools": 100},
    ) == (None, None)


def test_exact_match_is_selected_before_similar_candidates():
    apps = {
        "Steam": "C:\\Apps\\steam.exe",
        "Steem": "C:\\Apps\\steem.exe",
    }

    assert find_exact_match("steam", apps) == ("Steam", "C:\\Apps\\steam.exe")


def test_similar_apps_are_sorted_by_open_frequency(monkeypatch):
    apps = {
        "Steam": "C:\\Apps\\steam.exe",
        "Steam Tools": "C:\\Apps\\steam-tools.exe",
        "Steam Deck": "C:\\Apps\\steam-deck.exe",
    }
    monkeypatch.setattr(match_app, "_similarity", lambda _query, _name: 0.8)

    assert find_similar_apps(
        "steem",
        apps,
        open_counts={"Steam": 2, "Steam Tools": 100, "Steam Deck": 12},
    ) == [
        ("Steam Tools", "C:\\Apps\\steam-tools.exe"),
        ("Steam Deck", "C:\\Apps\\steam-deck.exe"),
        ("Steam", "C:\\Apps\\steam.exe"),
    ]


def test_prefix_matches_are_listed_before_fuzzy_matches(monkeypatch):
    apps = {
        "Steam Tools": "C:\\Apps\\steam-tools.exe",
        "Steam": "C:\\Apps\\steam.exe",
        "Other App": "C:\\Apps\\other.exe",
    }
    scores = {"steam tools": 0.7, "steam": 0.8, "other app": 0.99}
    monkeypatch.setattr(
        match_app,
        "_similarity",
        lambda _query, name: scores[name],
    )

    assert find_similar_apps(
        "ste",
        apps,
        open_counts={"Steam Tools": 1, "Steam": 2, "Other App": 100},
    ) == [
        ("Steam", "C:\\Apps\\steam.exe"),
        ("Steam Tools", "C:\\Apps\\steam-tools.exe"),
        ("Other App", "C:\\Apps\\other.exe"),
    ]


def test_prefix_matches_are_included_even_below_similarity_threshold():
    apps = {"Notepad++": "C:\\Apps\\notepad++.exe"}

    assert find_similar_apps("not", apps, threshold=0.99) == [
        ("Notepad++", "C:\\Apps\\notepad++.exe")
    ]
