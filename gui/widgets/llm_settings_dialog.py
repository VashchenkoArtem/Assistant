from uuid import uuid4

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import pyqtSignal

from utils.llm_config import (
    DEFAULT_PROVIDERS,
    LLMConfigError,
    ProviderSettings,
    load_credentials,
    load_preferences,
    normalize_anthropic_api_url,
    normalize_openai_api_url,
    save_credentials,
    save_preferences,
)


class AddOpenAIProviderDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Додати OpenAI-сумісний API")
        self.provider_config: ProviderSettings | None = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._name = QLineEdit()
        self._name.setPlaceholderText("Наприклад, OpenRouter")
        form.addRow("Назва:", self._name)
        self._provider_type = QComboBox()
        self._provider_type.addItem("OpenAI-сумісний", "openai_compatible")
        self._provider_type.addItem("Anthropic Messages API", "anthropic")
        self._provider_type.currentIndexChanged.connect(self._update_url_placeholder)
        form.addRow("Формат API:", self._provider_type)
        self._api_url = QLineEdit()
        self._api_url.setPlaceholderText("https://api.example.com/v1")
        form.addRow("URL API:", self._api_url)
        self._model = QLineEdit()
        self._model.setPlaceholderText("Ідентифікатор моделі у провайдера")
        form.addRow("Модель:", self._model)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_url_placeholder(self, _index: int) -> None:
        if self._provider_type.currentData() == "anthropic":
            self._api_url.setPlaceholderText("https://api.anthropic.com")
        else:
            self._api_url.setPlaceholderText("https://api.example.com/v1")

    def _validate_and_accept(self) -> None:
        name = self._name.text().strip()
        model = self._model.text().strip()
        if not name or not model:
            QMessageBox.critical(
                self,
                "Не вдалося додати провайдера",
                "Вкажіть назву провайдера та моделі.",
            )
            return
        provider_type = self._provider_type.currentData()
        try:
            if provider_type == "anthropic":
                api_url = normalize_anthropic_api_url(self._api_url.text())
            else:
                api_url = normalize_openai_api_url(self._api_url.text())
        except LLMConfigError as error:
            QMessageBox.critical(self, "Некоректна адреса API", str(error))
            return
        self.provider_config = {
            "name": name,
            "type": provider_type,
            "api_url": api_url,
            "model": model,
        }
        self.accept()


class LLMSettingsPanel(QWidget):
    back_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("llmSettingsPanel")

        self._preferences = load_preferences()
        self._credentials = load_credentials()
        self._model_fields: dict[str, QLineEdit] = {}
        self._key_lists: dict[str, QListWidget] = {}
        self._key_inputs: dict[str, QLineEdit] = {}
        self._provider_groups: dict[str, QGroupBox] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        title = QLabel("Персоналізація моделей")
        title.setObjectName("llmSettingsTitle")
        layout.addWidget(title)

        description = QLabel(
            "Додавайте необмежену кількість ключів, OpenAI-сумісні API та "
            "Anthropic Messages API. "
            "Ключі зберігаються локально у відкритому вигляді "
            "в ігнорованому Git файлі .llm_credentials.json."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self._fallback_checkbox = QCheckBox(
            "Автоматично перемикатися між ключами та провайдерами"
        )
        self._fallback_checkbox.setObjectName("llmFallbackEnabled")
        self._fallback_checkbox.setChecked(self._preferences["fallback_enabled"])
        layout.addWidget(self._fallback_checkbox)

        order_group = QGroupBox("Порядок провайдерів")
        order_layout = QHBoxLayout(order_group)
        self._provider_order = QListWidget()
        self._provider_order.setObjectName("llmProviderOrder")
        for provider_id in self._preferences["provider_order"]:
            self._add_provider_order_item(provider_id)
        order_layout.addWidget(self._provider_order, 1)

        order_buttons = QVBoxLayout()
        move_up = QPushButton("Вгору")
        move_up.clicked.connect(lambda: self._move_provider(-1))
        order_buttons.addWidget(move_up)
        move_down = QPushButton("Вниз")
        move_down.clicked.connect(lambda: self._move_provider(1))
        order_buttons.addWidget(move_down)
        add_provider = QPushButton("Додати API")
        add_provider.clicked.connect(self._add_provider)
        order_buttons.addWidget(add_provider)
        remove_provider = QPushButton("Видалити власний")
        remove_provider.clicked.connect(self._remove_provider)
        order_buttons.addWidget(remove_provider)
        order_buttons.addStretch(1)
        order_layout.addLayout(order_buttons)
        layout.addWidget(order_group)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        provider_container = QWidget()
        self._provider_layout = QVBoxLayout(provider_container)
        self._provider_layout.setContentsMargins(0, 0, 0, 0)
        for provider_id, provider_spec in self._preferences["providers"].items():
            self._add_provider_group(provider_id, provider_spec)
        self._provider_layout.addStretch(1)
        scroll.setWidget(provider_container)
        layout.addWidget(scroll, 1)

        footer = QHBoxLayout()
        self._save_status = QLabel()
        self._save_status.setObjectName("llmSaveStatus")
        footer.addWidget(self._save_status, 1)
        back_button = QPushButton("Назад до чату")
        back_button.clicked.connect(self.back_requested.emit)
        footer.addWidget(back_button)
        save_button = QPushButton("Зберегти")
        save_button.setObjectName("llmSaveButton")
        save_button.clicked.connect(self._save)
        footer.addWidget(save_button)
        layout.addLayout(footer)

    def _add_provider_order_item(self, provider_id: str) -> None:
        provider_spec = self._preferences["providers"][provider_id]
        self._provider_order.addItem(provider_spec["name"])
        item = self._provider_order.item(self._provider_order.count() - 1)
        if item is not None:
            item.setData(Qt.ItemDataRole.UserRole, provider_id)

    def _add_provider_group(
        self,
        provider_id: str,
        provider_spec: ProviderSettings,
    ) -> None:
        group = QGroupBox(provider_spec["name"])
        layout = QFormLayout(group)

        model = QLineEdit(provider_spec["model"])
        model.setObjectName(f"llmModel_{provider_id}")
        self._model_fields[provider_id] = model
        layout.addRow("Модель:", model)

        key_list = QListWidget()
        key_list.setObjectName(f"llmKeys_{provider_id}")
        key_list.setMaximumHeight(80)
        self._key_lists[provider_id] = key_list
        self._refresh_key_list(provider_id)
        layout.addRow("Збережені ключі:", key_list)

        key_row = QHBoxLayout()
        key_input = QLineEdit()
        key_input.setObjectName(f"llmNewKey_{provider_id}")
        key_input.setEchoMode(QLineEdit.EchoMode.Password)
        key_input.setPlaceholderText("Вставте API-ключ")
        self._key_inputs[provider_id] = key_input
        key_row.addWidget(key_input, 1)

        add_key = QPushButton("Додати ключ")
        add_key.clicked.connect(lambda: self._add_key(provider_id))
        key_row.addWidget(add_key)
        remove_key = QPushButton("Видалити вибраний")
        remove_key.clicked.connect(lambda: self._remove_key(provider_id))
        key_row.addWidget(remove_key)
        layout.addRow(key_row)

        self._provider_groups[provider_id] = group
        self._provider_layout.insertWidget(self._provider_layout.count() - 1, group)

    def _add_provider(self) -> None:
        dialog = AddOpenAIProviderDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.provider_config is None:
            return

        provider_id = f"custom_{uuid4().hex}"
        self._preferences["providers"][provider_id] = dialog.provider_config
        self._credentials[provider_id] = []
        self._add_provider_order_item(provider_id)
        self._add_provider_group(provider_id, dialog.provider_config)

    def _remove_provider(self) -> None:
        item = self._provider_order.currentItem()
        if item is None:
            return
        provider_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(provider_id, str) or provider_id not in self._preferences["providers"]:
            return
        if provider_id in DEFAULT_PROVIDERS:
            QMessageBox.information(
                self,
                "Вбудований провайдер",
                "Вбудовані провайдери не можна видалити. Видаліть їхні ключі або "
                "перемістіть нижче у списку.",
            )
            return
        confirmation = QMessageBox.question(
            self,
            "Видалити провайдера",
            "Буде видалено налаштування провайдера та його ключі. Продовжити?",
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        row = self._provider_order.row(item)
        self._provider_order.takeItem(row)
        del self._preferences["providers"][provider_id]
        self._credentials.pop(provider_id, None)
        self._model_fields.pop(provider_id, None)
        self._key_lists.pop(provider_id, None)
        self._key_inputs.pop(provider_id, None)
        group = self._provider_groups.pop(provider_id)
        self._provider_layout.removeWidget(group)
        group.deleteLater()

    def _refresh_key_list(self, provider_id: str) -> None:
        key_list = self._key_lists[provider_id]
        key_list.clear()
        for index, _key in enumerate(self._credentials.get(provider_id, []), start=1):
            key_list.addItem(f"Ключ {index}")

    def _add_key(self, provider_id: str) -> None:
        key_input = self._key_inputs[provider_id]
        key = key_input.text().strip()
        if not key:
            return
        if any(character.isspace() for character in key):
            QMessageBox.warning(
                self,
                "Некоректний API-ключ",
                "Вставте лише сам ключ одним рядком, без пробілів чи коду прикладу.",
            )
            return
        provider_keys = self._credentials.setdefault(provider_id, [])
        if key not in provider_keys:
            provider_keys.append(key)
            self._refresh_key_list(provider_id)
        key_input.clear()

    def _remove_key(self, provider_id: str) -> None:
        key_list = self._key_lists[provider_id]
        selected_row = key_list.currentRow()
        provider_keys = self._credentials[provider_id]
        if 0 <= selected_row < len(provider_keys):
            del provider_keys[selected_row]
            self._refresh_key_list(provider_id)

    def _move_provider(self, offset: int) -> None:
        current_row = self._provider_order.currentRow()
        target_row = current_row + offset
        if current_row < 0 or not 0 <= target_row < self._provider_order.count():
            return
        item = self._provider_order.takeItem(current_row)
        self._provider_order.insertItem(target_row, item)
        self._provider_order.setCurrentRow(target_row)

    def _save(self) -> None:
        provider_order = []
        for index in range(self._provider_order.count()):
            item = self._provider_order.item(index)
            if item is not None:
                provider_order.append(item.data(Qt.ItemDataRole.UserRole))
        if any(not field.text().strip() for field in self._model_fields.values()):
            QMessageBox.critical(
                self,
                "Не вдалося зберегти",
                "Вкажіть назву моделі для кожного провайдера.",
            )
            return

        providers = {
            provider_id: {
                **self._preferences["providers"][provider_id],
                "model": field.text().strip(),
            }
            for provider_id, field in self._model_fields.items()
        }
        preferences = {
            "fallback_enabled": self._fallback_checkbox.isChecked(),
            "provider_order": provider_order,
            "providers": providers,
        }
        credentials = {
            provider_id: self._credentials.get(provider_id, [])
            for provider_id in providers
        }
        try:
            save_credentials(credentials)
            save_preferences(preferences)
        except LLMConfigError as error:
            QMessageBox.critical(self, "Не вдалося зберегти", str(error))
            return
        self._save_status.setText("Налаштування збережено.")
