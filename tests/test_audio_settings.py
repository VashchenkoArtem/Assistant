import os
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from gui.main_window import MainWindow
from gui.widgets.settings import audio_settings_dialog
from utils import audio_settings


def test_audio_settings_are_saved_and_loaded(tmp_path, monkeypatch):
    settings = QSettings(
        str(tmp_path / "audio.ini"),
        QSettings.Format.IniFormat,
    )
    monkeypatch.setattr(audio_settings, "_settings", lambda: settings)

    audio_settings.save_audio_settings(2, "Headphones", 65)

    assert audio_settings.get_microphone_device_index() == 2
    assert audio_settings.get_output_device_name() == "Headphones"
    assert audio_settings.get_output_volume() == 0.65


def test_audio_settings_reject_invalid_values(tmp_path, monkeypatch):
    settings = QSettings(
        str(tmp_path / "audio.ini"),
        QSettings.Format.IniFormat,
    )
    monkeypatch.setattr(audio_settings, "_settings", lambda: settings)

    with pytest.raises(ValueError, match="мікрофона"):
        audio_settings.save_audio_settings(-2, "", 50)

    with pytest.raises(ValueError, match="Гучність"):
        audio_settings.save_audio_settings(-1, "", 101)


def test_audio_settings_page_is_internal_and_reuses_instance(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        audio_settings_dialog,
        "list_microphone_devices",
        lambda: [(0, "Built-in microphone")],
    )
    monkeypatch.setattr(
        audio_settings_dialog,
        "list_output_devices",
        lambda: ["Speakers"],
    )
    window = MainWindow(command=object())

    window.open_audio_settings()
    panel = window._audio_settings_panel

    assert panel is not None
    assert window._content_stack.currentWidget() is panel
    window.open_audio_settings()
    assert window._audio_settings_panel is panel

    window.close()
    app.processEvents()


def test_audio_settings_dialog_saves_selected_devices_and_volume(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        audio_settings_dialog,
        "list_microphone_devices",
        lambda: [(0, "Built-in microphone"), (1, "USB microphone")],
    )
    monkeypatch.setattr(
        audio_settings_dialog,
        "list_output_devices",
        lambda: ["Speakers", "Headphones"],
    )
    saved_settings = []
    monkeypatch.setattr(
        audio_settings_dialog,
        "save_audio_settings",
        lambda *values: saved_settings.append(values),
    )
    dialog = audio_settings_dialog.AudioSettingsDialog()
    dialog.microphone.setCurrentIndex(dialog.microphone.findData(1))
    dialog.output_device.setCurrentIndex(dialog.output_device.findData("Headphones"))
    dialog.volume.setValue(42)

    dialog._save()

    assert saved_settings == [(1, "Headphones", 42)]
    assert dialog.status.text() == "Налаштування збережено."

    dialog.close()
    app.processEvents()


def test_voice_worker_uses_selected_microphone(monkeypatch):
    import speech_recognition

    from gui.workers import VoiceWorker

    selected_devices = []

    class Microphone:
        def __init__(self, device_index):
            selected_devices.append(device_index)

        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        "gui.workers.get_microphone_device_index",
        lambda: 3,
    )
    monkeypatch.setattr(speech_recognition, "Microphone", Microphone)
    worker = VoiceWorker()
    worker.stop()

    with patch("gui.workers.configure_recognizer"):
        worker.run()

    assert selected_devices == [3]


def test_voice_output_uses_selected_device_and_volume(monkeypatch):
    from types import SimpleNamespace

    from utils import voicing_answer

    mixer_calls = []
    volume_levels = []
    mixer = SimpleNamespace(
        get_init=lambda: None,
        init=lambda **kwargs: mixer_calls.append(kwargs),
        Sound=lambda _file_name: SimpleNamespace(
            set_volume=volume_levels.append,
        ),
    )
    monkeypatch.setattr(
        voicing_answer,
        "pygame",
        SimpleNamespace(mixer=mixer),
    )
    monkeypatch.setattr(voicing_answer, "_mixer_device_name", None)
    monkeypatch.setattr(voicing_answer, "get_output_device_name", lambda: "Headphones")
    monkeypatch.setattr(voicing_answer, "get_output_volume", lambda: 0.4)

    sound = voicing_answer._create_audio_sound("voice.mp3")

    assert sound is not None
    assert mixer_calls == [{"devicename": "Headphones"}]
    assert volume_levels == [0.4]
