import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication

from gui.widgets.controls.composer import Composer


def test_composer_send_button_follows_prompt_and_sits_after_microphone():
    app = QApplication.instance() or QApplication([])
    composer = Composer()
    submitted = []
    composer.submitted.connect(submitted.append)
    parent = composer.prompt.parentWidget()
    assert parent is not None
    controls = parent.layout()
    assert controls is not None
    control_order = []
    for index in range(controls.count()):
        item = controls.itemAt(index)
        assert item is not None
        widget = item.widget()
        assert widget is not None
        control_order.append(widget)

    assert control_order == [
        composer.prompt,
        composer.microphone,
        composer.send_button,
    ]
    assert not composer.send_button.isEnabled()
    inactive_icon = (
        composer.send_button.icon()
        .pixmap(QSize(20, 20))
        .toImage()
        .pixelColor(10, 10)
    )

    composer.prompt.setPlainText("  ")
    assert not composer.send_button.isEnabled()
    assert (
        composer.send_button.icon().pixmap(QSize(20, 20)).toImage().pixelColor(10, 10)
        == inactive_icon
    )

    composer.prompt.setPlainText(" hello ")
    assert composer.send_button.isEnabled()
    assert (
        composer.send_button.icon().pixmap(QSize(20, 20)).toImage().pixelColor(10, 10)
        != inactive_icon
    )

    composer.set_prompt_enabled(False)
    assert not composer.send_button.isEnabled()
    composer.set_prompt_enabled(True)
    assert composer.send_button.isEnabled()

    composer.send_button.click()
    assert submitted == ["hello"]
    assert not composer.send_button.isEnabled()
    assert app is not None
    composer.close()
