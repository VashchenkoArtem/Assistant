import json
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QDialog, QLineEdit, QMessageBox

from gui.main_window import MainWindow
from gui.widgets.settings.llm_settings_dialog import (
    AddOpenAIProviderDialog,
    LLMSettingsPanel,
)
from utils import llm_config


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def local_llm_files(monkeypatch, tmp_path):
    credentials_file = tmp_path / ".llm_credentials.json"
    preferences_file = tmp_path / ".llm_preferences.json"
    monkeypatch.setattr(llm_config, "CREDENTIALS_FILE", credentials_file)
    monkeypatch.setattr(llm_config, "PREFERENCES_FILE", preferences_file)
    return credentials_file, preferences_file


def test_personalization_panel_saves_keys_models_and_order(
    qt_app,
    local_llm_files,
):
    credentials_file, preferences_file = local_llm_files
    panel = LLMSettingsPanel()

    groq_key = panel.findChild(QLineEdit, "llmNewKey_groq")
    assert groq_key is not None
    groq_key.setText("groq-private-key")
    panel._add_key("groq")
    for index in range(1, 21):
        groq_key.setText(f"groq-private-key-{index}")
        panel._add_key("groq")
    panel._model_fields["groq"].setText("custom-groq-model")
    panel._provider_order.setCurrentRow(1)
    panel._move_provider(-1)
    panel._save()

    credentials = json.loads(credentials_file.read_text(encoding="utf-8"))
    assert credentials["groq"] == [
        "groq-private-key",
        *(f"groq-private-key-{index}" for index in range(1, 21)),
    ]
    assert credentials["gemini"] == []
    saved_preferences = json.loads(preferences_file.read_text(encoding="utf-8"))
    assert saved_preferences["provider_order"] == ["gemini", "groq"]
    assert saved_preferences["providers"]["groq"]["model"] == "custom-groq-model"
    assert "private" not in preferences_file.read_text(encoding="utf-8")
    assert panel._save_status.text() == "Налаштування збережено."
    assert qt_app is not None


def test_personalization_panel_rejects_multiline_api_key(qt_app, local_llm_files):
    credentials_file = local_llm_files[0]
    panel = LLMSettingsPanel()
    key_input = panel.findChild(QLineEdit, "llmNewKey_groq")
    assert key_input is not None
    key_input.setText("test-key\nextra-line")

    with patch.object(QMessageBox, "warning") as warning:
        panel._add_key("groq")

    assert not panel._credentials.get("groq")
    assert not credentials_file.exists()
    warning.assert_called_once()
    assert qt_app is not None


def test_sidebar_switches_between_chat_and_embedded_personalization(
    qt_app,
    local_llm_files,
):
    credentials_file, preferences_file = local_llm_files
    window = MainWindow(command=object())
    window.show()
    qt_app.processEvents()

    assert window.search.isVisible()
    window.sidebar._page_buttons["profile"].click()
    qt_app.processEvents()

    assert window._settings_panel is not None
    assert window._content_stack.currentWidget() is window._settings_panel
    assert window._settings_panel.isVisible()
    assert not window.search.isVisible()

    window._settings_panel.back_requested.emit()
    qt_app.processEvents()

    assert window._content_stack.currentWidget() is window._chat_page
    assert window.search.isVisible()
    assert window.sidebar._page_buttons["home"].isChecked()
    assert not credentials_file.exists()
    assert not preferences_file.exists()
    window.close()
    assert qt_app is not None


def test_custom_provider_dialog_accepts_anthropic_api(qt_app):
    dialog = AddOpenAIProviderDialog()
    dialog._name.setText("Anthropic")
    dialog._provider_type.setCurrentIndex(1)
    dialog._api_url.setText("https://api.anthropic.com")
    dialog._model.setText("claude-model")

    dialog._validate_and_accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.provider_config == {
        "name": "Anthropic",
        "type": "anthropic",
        "api_url": "https://api.anthropic.com/v1/messages",
        "model": "claude-model",
    }
    assert qt_app is not None


def test_main_window_uses_ready_initialization_worker(qt_app):
    with (
        patch("gui.main_window.InitializationWorker") as worker_class,
        patch("gui.main_window.QThreadPool.start"),
    ):
        window = MainWindow()

    finished_callback = (
        worker_class.return_value.signals.finished.connect.call_args.args[0]
    )
    finished_callback("initialized-command", None)

    assert window._command == "initialized-command"
    assert not window._initializing
    window.close()
    assert qt_app is not None
