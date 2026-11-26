import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QToolButton

from gui.icon_loader import icon_path, load_pixmap
from gui.widgets.common.icons import icon_path as widget_icon_path
from gui.widgets.navigation.sidebar import Sidebar
from gui.widgets.navigation.title_bar import TitleBar


def test_window_control_icons_render_without_deleted_png_assets():
    app = QApplication.instance() or QApplication([])

    for name in (
        "window/close_winow.svg",
        "window/full_window.svg",
        "window/hide_window.svg",
    ):
        pixmap = load_pixmap(icon_path(name), 40)
        assert not pixmap.isNull()
        assert pixmap.width() > 0
        assert pixmap.height() > 0

    assert app is not None


def test_icons_in_purpose_folders_are_loadable():
    app = QApplication.instance() or QApplication([])
    icons_dir = Path(__file__).parents[1] / "gui" / "assets" / "icons"
    icon_paths = tuple(icons_dir.rglob("*.svg"))

    assert icon_paths
    for path in icon_paths:
        relative_path = path.relative_to(icons_dir).as_posix()
        assert not load_pixmap(icon_path(relative_path), 24).isNull()

    assert app is not None


def test_widget_icon_paths_resolve_to_existing_assets():
    for name in (
        "branding/logo_assistant.svg",
        "chat/bot_ico.svg",
        "chat/info.svg",
        "chat/user_ico.svg",
        "controls/micro.svg",
        "controls/micro_off.svg",
        "controls/search.svg",
        "controls/system_enter.svg",
        "navigation/home.svg",
        "navigation/settings.svg",
        "status/status.svg",
        "window/close_winow.svg",
        "window/full_window.svg",
        "window/hide_window.svg",
    ):
        assert widget_icon_path(name).is_file()


def test_missing_icon_path_is_reported():
    missing_path = Path(__file__).parent / "missing-icon.svg"

    with pytest.raises(FileNotFoundError):
        load_pixmap(missing_path, 20)


def test_title_bar_contains_window_control_buttons():
    app = QApplication.instance() or QApplication([])
    calls = []
    bar = TitleBar(
        minimize_callback=lambda: calls.append("minimize"),
        maximize_callback=lambda: calls.append("maximize"),
        close_callback=lambda: calls.append("close"),
    )

    buttons = bar.findChildren(QToolButton)
    assert len(buttons) == 3

    for button in buttons:
        button.click()

    assert calls == ["minimize", "maximize", "close"]


def test_sidebar_expands_and_collapses_without_losing_active_page():
    app = QApplication.instance() or QApplication([])
    sidebar = Sidebar()
    sidebar.set_active_page("settings")
    logo_button = sidebar.findChild(QToolButton, "sidebarLogo")
    page_buttons = sidebar.findChildren(QToolButton, "sideButton")

    assert logo_button is not None
    assert len(page_buttons) == 3
    assert sidebar.width() == 63
    assert next(
        button for button in page_buttons if button.toolTip() == "Налаштування"
    ).isChecked()

    logo_button.click()

    assert sidebar.width() == 220
    assert all(
        button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        for button in page_buttons
    )
    assert next(
        button for button in page_buttons if button.toolTip() == "Налаштування"
    ).isChecked()

    logo_button.click()

    assert sidebar.width() == 63
    assert all(
        button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
        for button in page_buttons
    )
    assert app is not None
