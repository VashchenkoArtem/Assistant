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


def test_microphone_device_names_repair_mojibake_without_changing_valid_names(
    monkeypatch,
):
    from types import SimpleNamespace

    import speech_recognition

    devices = [
        {
            "name": "РџРµСЂРµРЅР°Р·РЅР°С‡РµРЅРёРµ - Input",
            "maxInputChannels": 2,
        },
        {"name": "Output only", "maxInputChannels": 0},
        {"name": "Микрофон (Realtek(R) Audio)", "maxInputChannels": 1},
    ]

    class Audio:
        terminated = False

        def get_device_count(self):
            return len(devices)

        def get_device_info_by_index(self, index):
            return devices[index]

        def terminate(self):
            self.terminated = True

    audio = Audio()
    pyaudio = SimpleNamespace(PyAudio=lambda: audio)
    monkeypatch.setattr(
        speech_recognition.Microphone,
        "get_pyaudio",
        staticmethod(lambda: pyaudio),
    )
    monkeypatch.setattr(audio_settings.sys, "platform", "win32")
    monkeypatch.setattr(
        audio_settings,
        "_list_active_windows_microphone_names",
        lambda: {
            "переназначение - input",
            "микрофон (realtek(r) audio)",
        },
    )

    assert audio_settings.list_microphone_devices() == [
        (0, "Переназначение - Input"),
        (2, "Микрофон (Realtek(R) Audio)"),
    ]
    assert audio.terminated


def test_microphone_list_excludes_inactive_windows_endpoints(monkeypatch):
    from types import SimpleNamespace

    import speech_recognition

    devices = [
        {"name": "USB Microphone", "maxInputChannels": 1},
        {"name": "Disabled Microphone", "maxInputChannels": 1},
        {"name": "USB Microphone", "maxInputChannels": 1},
    ]

    class Audio:
        def get_device_count(self):
            return len(devices)

        def get_device_info_by_index(self, index):
            return devices[index]

        def terminate(self):
            pass

    pyaudio = SimpleNamespace(PyAudio=Audio)
    monkeypatch.setattr(
        speech_recognition.Microphone,
        "get_pyaudio",
        staticmethod(lambda: pyaudio),
    )
    monkeypatch.setattr(audio_settings.sys, "platform", "win32")
    monkeypatch.setattr(
        audio_settings,
        "_list_active_windows_microphone_names",
        lambda: {"usb microphone"},
    )

    assert audio_settings.list_microphone_devices() == [(0, "USB Microphone")]


def test_unavailable_saved_microphone_falls_back_to_system_default(monkeypatch):
    monkeypatch.setattr(audio_settings, "get_microphone_device_index", lambda: 26)
    monkeypatch.setattr(
        audio_settings,
        "list_microphone_devices",
        lambda: [(index, f"Microphone {index}") for index in range(26)],
    )

    assert audio_settings.resolve_microphone_device_index() is None


def test_available_saved_microphone_index_is_preserved(monkeypatch):
    monkeypatch.setattr(audio_settings, "get_microphone_device_index", lambda: 3)
    monkeypatch.setattr(
        audio_settings,
        "list_microphone_devices",
        lambda: [(3, "USB microphone")],
    )

    assert audio_settings.resolve_microphone_device_index() == 3


def test_system_default_microphone_does_not_enumerate_saved_devices(monkeypatch):
    monkeypatch.setattr(audio_settings, "get_microphone_device_index", lambda: -1)
    monkeypatch.setattr(
        audio_settings,
        "list_microphone_devices",
        lambda: pytest.fail("default input should not require device enumeration"),
    )

    assert audio_settings.resolve_microphone_device_index() is None


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


def test_audio_settings_dialog_shows_default_for_unavailable_saved_device(
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        audio_settings_dialog,
        "get_microphone_device_index",
        lambda: 26,
    )
    monkeypatch.setattr(
        audio_settings_dialog,
        "list_microphone_devices",
        lambda: [(1, "Built-in microphone")],
    )
    monkeypatch.setattr(
        audio_settings_dialog,
        "list_output_devices",
        lambda: ["Speakers"],
    )
    dialog = audio_settings_dialog.AudioSettingsDialog()

    assert dialog.microphone.currentData() == -1
    assert "мікрофон недоступний" in dialog.status.text()

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

    monkeypatch.setattr(speech_recognition, "Microphone", Microphone)
    worker = VoiceWorker(device_index=3)
    worker.stop()

    with patch("gui.workers.configure_recognizer"):
        worker.run()

    assert selected_devices == [3]


def test_voice_worker_uses_system_default_microphone(monkeypatch):
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

    monkeypatch.setattr(speech_recognition, "Microphone", Microphone)
    worker = VoiceWorker(device_index=None)
    worker.stop()

    with patch("gui.workers.configure_recognizer"):
        worker.run()

    assert selected_devices == [None]


def test_main_window_passes_resolved_microphone_to_voice_worker(
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "gui.main_window.resolve_microphone_device_index",
        lambda: 1,
    )
    monkeypatch.setattr("gui.main_window.QThreadPool.start", lambda *_args: None)
    window = MainWindow(command=object())

    window.start_microphone_input()

    assert window._voice_worker is not None
    assert window._voice_worker.device_index == 1
    window.close()
    app.processEvents()


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
