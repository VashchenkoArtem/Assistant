import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from gui.widgets.chat.chat_panel import ChatPanel


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def test_new_command_scrolls_to_bottom_after_layout_updates(qt_app):
    chat = ChatPanel()
    chat.setFixedSize(360, 220)
    chat.show()
    for index in range(20):
        chat.add_card("Поліна", f"Повідомлення {index} " + "текст " * 20)
    qt_app.processEvents()
    chat.add_card("Поліна", "Підготовка до перевірки прокрутки")
    qt_app.processEvents()

    scrollbar = chat.scroll_area.verticalScrollBar()
    assert scrollbar.maximum() > 0
    scrollbar.setValue(scrollbar.maximum())

    chat.add_card("Користувач", "Нова команда", is_user=True)
    qt_app.processEvents()

    assert scrollbar.value() == scrollbar.maximum()
    chat.close()
