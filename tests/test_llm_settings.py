import json
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QEvent, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
)

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
    groq_key.setText("gsk_test-key")
    panel._add_key("groq")
    for index in range(1, 21):
        groq_key.setText(f"gsk_test-key-{index}")
        panel._add_key("groq")
    panel._model_fields["groq"].setText("custom-groq-model")
    panel._provider_order.setCurrentRow(1)
    panel._move_provider(-1)
    panel._save()

    credentials = json.loads(credentials_file.read_text(encoding="utf-8"))
    assert credentials["groq"] == [
        "gsk_test-key",
        *(f"gsk_test-key-{index}" for index in range(1, 21)),
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

    panel._add_key("groq")

    assert not panel._credentials.get("groq")
    assert not credentials_file.exists()
    assert panel._key_error_labels["groq"].isHidden() is False
    assert "рядком" in panel._key_error_labels["groq"].text()
    assert qt_app is not None


def test_personalization_panel_validates_key_format_and_duplicates(
    qt_app,
    local_llm_files,
):
    panel = LLMSettingsPanel()
    key_input = panel.findChild(QLineEdit, "llmNewKey_groq")
    assert key_input is not None

    key_input.setText("not-a-groq-key")
    assert panel._validate_key_input("groq") == (
        "Ключ для Groq має починатися з «gsk_»."
    )
    assert key_input.property("invalid") is True

    key_input.setText("gsk_valid-test-key")
    panel._add_key("groq")
    key_input.setText("gsk_valid-test-key")
    assert panel._validate_key_input("groq") == "Цей API-ключ уже додано."

    key_input.setText("Bearer gsk-valid-test-key")
    assert "тільки сам ключ" in panel._validate_key_input("groq")

    assert qt_app is not None


def test_key_validation_message_uses_compact_row(qt_app, local_llm_files):
    panel = LLMSettingsPanel()
    panel.show()
    qt_app.processEvents()
    key_input = panel._key_inputs["groq"]
    error_label = panel._key_error_labels["groq"]

    panel._set_key_error("groq", "API-ключ занадто короткий.")
    qt_app.processEvents()

    assert error_label.geometry().top() >= key_input.geometry().bottom()
    assert error_label.height() < 40
    assert qt_app is not None


def test_provider_test_message_stays_below_test_button(
    qt_app,
    local_llm_files,
):
    panel = LLMSettingsPanel()
    panel.show()
    qt_app.processEvents()
    status = panel.findChild(QLabel, "llmProviderStatusText_groq")
    test_button = panel.findChild(QPushButton, "llmTest_groq")
    assert status is not None
    assert test_button is not None

    model_field = panel._model_fields["groq"]
    key_list = panel._key_lists["groq"]
    panel._set_provider_test_status(
        "groq",
        "Помилка авторизації LLM API. Перевірте API-ключ.",
    )
    qt_app.processEvents()

    assert status.geometry().top() >= test_button.geometry().bottom()
    assert status.height() < 60
    assert model_field.geometry().top() < 80
    assert panel._key_inputs["groq"].geometry().top() - key_list.geometry().bottom() < 30
    assert qt_app is not None


def test_personalization_panel_uses_provider_cards_and_unsaved_status(
    qt_app,
    local_llm_files,
):
    panel = LLMSettingsPanel()

    assert panel._provider_order.count() >= 2
    assert panel._provider_editor.count() >= 2
    panel._provider_order.setCurrentRow(0)
    assert panel._provider_editor.currentWidget() is panel._provider_groups[
        panel._provider_order.item(0).data(Qt.ItemDataRole.UserRole)
    ]

    panel._model_fields["groq"].setText("new-groq-model")

    assert panel._save_status.text() == "Є незбережені зміни"
    assert qt_app is not None


def test_move_provider_keeps_card_visible(
    qt_app,
    local_llm_files,
):
    panel = LLMSettingsPanel()
    panel.show()
    qt_app.processEvents()
    panel._provider_order.setCurrentRow(1)
    moved_provider_id = panel._provider_order.currentItem().data(
        Qt.ItemDataRole.UserRole
    )
    old_card = panel._provider_order.itemWidget(
        panel._provider_order.currentItem()
    )

    panel._move_provider(-1)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_app.processEvents()

    moved_item = panel._provider_order.item(0)
    moved_card = panel._provider_order.itemWidget(moved_item)
    assert moved_item.data(Qt.ItemDataRole.UserRole) == moved_provider_id
    assert moved_card is not None
    assert moved_card is not old_card
    assert moved_card.isVisible()
    assert panel._provider_cards[moved_provider_id][0] is moved_card
    assert panel._provider_editor.currentWidget() is panel._provider_groups[
        moved_provider_id
    ]
    assert qt_app is not None


def test_remove_custom_provider_cleans_status_widgets(
    qt_app,
    local_llm_files,
):
    panel = LLMSettingsPanel()
    provider_id = "custom_test"
    provider_spec = {
        "name": "Test Provider",
        "type": "openai_compatible",
        "api_url": "https://api.example.com/v1",
        "model": "test-model",
    }
    panel._preferences["providers"][provider_id] = provider_spec
    panel._credentials[provider_id] = ["test-key"]
    panel._add_provider_order_item(provider_id)
    panel._add_provider_group(provider_id, provider_spec)
    item = panel._provider_order.item(panel._provider_order.count() - 1)
    panel._provider_order.setCurrentItem(item)

    with patch.object(
        QMessageBox,
        "question",
        return_value=QMessageBox.StandardButton.Yes,
    ):
        panel._remove_provider()

    assert provider_id not in panel._preferences["providers"]
    assert provider_id not in panel._provider_cards
    assert provider_id not in panel._provider_groups
    assert provider_id not in panel._credentials
    assert provider_id not in panel._preferences["provider_order"]
    remaining_row = panel._provider_order.currentRow()
    assert remaining_row >= 0
    assert panel._provider_editor.currentWidget() is panel._provider_groups[
        panel._provider_order.item(remaining_row).data(Qt.ItemDataRole.UserRole)
    ]

    panel._refresh_provider_statuses()
    panel._status_timer.timeout.emit()
    assert qt_app is not None


def test_default_providers_can_be_removed_and_restored(
    qt_app,
    local_llm_files,
):
    panel = LLMSettingsPanel()
    panel._credentials["groq"] = ["gsk_test-key"]

    with patch.object(
        QMessageBox,
        "question",
        return_value=QMessageBox.StandardButton.Yes,
    ):
        panel._provider_order.setCurrentRow(0)
        panel._remove_provider()
        assert "groq" not in panel._preferences["providers"]
        assert "groq" not in panel._credentials

        panel._provider_order.setCurrentRow(0)
        panel._remove_provider()

    assert panel._provider_order.count() == 0
    assert panel._provider_editor.currentWidget() is panel._provider_editor_empty
    assert panel._restore_defaults_button.isEnabled()

    panel._save()
    assert llm_config.load_preferences()["providers"] == {}
    assert llm_config.load_preferences()["provider_order"] == []

    panel._restore_default_providers()

    assert panel._preferences["provider_order"] == ["groq", "gemini"]
    assert panel._credentials["groq"] == []
    assert not panel._restore_defaults_button.isEnabled()
    panel._save()
    assert llm_config.load_preferences()["provider_order"] == ["groq", "gemini"]
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
