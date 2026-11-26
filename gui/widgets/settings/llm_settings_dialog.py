from uuid import uuid4

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QHideEvent, QShowEvent
from PyQt6 import sip
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
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QFrame,
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
    validate_api_key,
)
from utils import llm_client


class AddProviderDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Додати API провайдера")
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


AddOpenAIProviderDialog = AddProviderDialog


class LLMSettingsPanel(QWidget):
    back_requested = pyqtSignal()
    saved = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("llmSettingsPanel")

        self._preferences = load_preferences()
        self._credentials = load_credentials()
        self._model_fields: dict[str, QLineEdit] = {}
        self._key_lists: dict[str, QListWidget] = {}
        self._key_inputs: dict[str, QLineEdit] = {}
        self._provider_groups: dict[str, QGroupBox] = {}
        self._provider_ids: dict[int, str] = {}
        self._provider_cards: dict[str, tuple[QFrame, QLabel, QLabel]] = {}
        self._key_error_labels: dict[str, QLabel] = {}
        self._custom_fields: dict[str, dict[str, QWidget]] = {}
        self._dirty = False
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(1000)
        self._status_timer.timeout.connect(self._refresh_provider_statuses)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(8)

        title = QLabel("Персоналізація моделей")
        title.setObjectName("llmSettingsTitle")
        layout.addWidget(title)

        description = QLabel(
            "Провайдери, моделі й ключі асистента. Порядок у списку визначає "
            "чергу резервування."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self._availability_banner = QLabel()
        self._availability_banner.setObjectName("llmAvailabilityBanner")
        self._availability_banner.setWordWrap(True)
        self._availability_banner.hide()
        layout.addWidget(self._availability_banner)

        security_warning = QLabel(
            "Ключі зберігаються локально у відкритому вигляді в файлі "
            ".llm_credentials.json. Не надсилайте цей файл."
        )
        security_warning.setObjectName("llmSecurityWarning")
        security_warning.setWordWrap(True)
        layout.addWidget(security_warning)

        self._fallback_checkbox = QCheckBox(
            "Автоматично перемикатися між ключами та провайдерами"
        )
        self._fallback_checkbox.setObjectName("llmFallbackEnabled")
        self._fallback_checkbox.setChecked(self._preferences["fallback_enabled"])
        self._fallback_checkbox.toggled.connect(self._mark_dirty)
        layout.addWidget(self._fallback_checkbox)

        order_group = QGroupBox("Порядок провайдерів")
        order_layout = QHBoxLayout(order_group)
        order_layout.setContentsMargins(0, 0, 0, 0)
        order_layout.setSpacing(12)

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(8)
        self._provider_order = QListWidget()
        self._provider_order.setObjectName("llmProviderOrder")
        for provider_id in self._preferences["provider_order"]:
            self._add_provider_order_item(provider_id)
        self._provider_order.currentRowChanged.connect(self._select_provider)
        left_layout.addWidget(self._provider_order, 1)

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
        remove_provider = QPushButton("Видалити вибраний")
        remove_provider.clicked.connect(self._remove_provider)
        order_buttons.addWidget(remove_provider)
        self._restore_defaults_button = QPushButton("Відновити рекомендовані")
        self._restore_defaults_button.clicked.connect(
            self._restore_default_providers
        )
        order_buttons.addWidget(self._restore_defaults_button)
        self._update_restore_defaults_button()
        order_buttons.addStretch(1)
        left_layout.addLayout(order_buttons)
        order_layout.addWidget(left_container, 44)

        self._provider_editor = QStackedWidget()
        order_layout.addWidget(self._provider_editor, 56)
        self._provider_editor_empty = QLabel("Немає провайдерів")
        self._provider_editor_empty.setObjectName("llmProviderEditorEmpty")
        self._provider_editor_empty.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self._provider_editor.addWidget(self._provider_editor_empty)
        layout.addWidget(order_group)
        for provider_id, provider_spec in self._preferences["providers"].items():
            self._add_provider_group(provider_id, provider_spec)
        if self._provider_order.count():
            self._provider_order.setCurrentRow(0)
        self._refresh_provider_statuses()
        self._status_timer.start()

        footer = QHBoxLayout()
        self._save_status = QLabel()
        self._save_status.setObjectName("llmSaveStatus")
        footer.addWidget(self._save_status, 1)
        back_button = QPushButton("Назад до чату")
        back_button.clicked.connect(self._back)
        footer.addWidget(back_button)
        save_button = QPushButton("Зберегти")
        save_button.setObjectName("llmSaveButton")
        save_button.clicked.connect(self._save)
        footer.addWidget(save_button)
        layout.addLayout(footer)

    def _add_provider_order_item(self, provider_id: str) -> None:
        provider_spec = self._preferences["providers"][provider_id]
        row = self._provider_order.count()
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, provider_id)
        self._provider_order.addItem(item)
        card = QFrame()
        card.setObjectName("llmProviderCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 8, 10, 8)
        card_layout.setSpacing(4)

        top = QHBoxLayout()
        number = QLabel(str(row + 1))
        number.setObjectName("llmProviderNumber")
        number.setFixedSize(22, 22)
        number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(number)

        name = QLabel(provider_spec["name"])
        name.setObjectName("llmProviderName")
        top.addWidget(name, 1)
        status = QLabel("Готовий")
        status.setObjectName("llmProviderStatusReady")
        top.addWidget(status)
        card_layout.addLayout(top)

        model = QLabel(provider_spec["model"])
        model.setObjectName("llmProviderModel")
        card_layout.addWidget(model)

        keys = QLabel("0 ключів")
        keys.setObjectName("llmProviderKeys")
        card_layout.addWidget(keys)
        item.setSizeHint(card.sizeHint().expandedTo(card.minimumSizeHint()))
        self._provider_order.setItemWidget(item, card)
        self._provider_cards[provider_id] = (card, status, keys)

    def _add_provider_group(
        self,
        provider_id: str,
        provider_spec: ProviderSettings,
    ) -> None:
        group = QGroupBox(provider_spec["name"])
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(14, 12, 14, 12)
        group_layout.setSpacing(8)
        layout = QFormLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        group_layout.addLayout(layout)
        group_layout.addStretch(1)

        if provider_id not in DEFAULT_PROVIDERS:
            custom_fields: dict[str, QWidget] = {}
            name = QLineEdit(provider_spec["name"])
            name.setObjectName(f"llmName_{provider_id}")
            name.textChanged.connect(self._mark_dirty)
            custom_fields["name"] = name
            layout.addRow("Назва:", name)

            provider_type = QComboBox()
            provider_type.addItem("OpenAI-сумісний", "openai_compatible")
            provider_type.addItem("Anthropic Messages API", "anthropic")
            provider_type.setObjectName(f"llmType_{provider_id}")
            provider_type.setCurrentIndex(
                1 if provider_spec["type"] == "anthropic" else 0
            )
            provider_type.currentIndexChanged.connect(self._mark_dirty)
            custom_fields["type"] = provider_type
            layout.addRow("Формат API:", provider_type)

            api_url = QLineEdit(provider_spec["api_url"])
            api_url.setObjectName(f"llmUrl_{provider_id}")
            api_url.textChanged.connect(self._mark_dirty)
            custom_fields["url"] = api_url
            layout.addRow("URL API:", api_url)
            self._custom_fields[provider_id] = custom_fields

        model = QLineEdit(provider_spec["model"])
        model.setObjectName(f"llmModel_{provider_id}")
        model.textChanged.connect(self._mark_dirty)
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

        key_error = QLabel()
        key_error.setObjectName(f"llmKeyError_{provider_id}")
        key_error.setProperty("llmKeyError", True)
        key_error.setWordWrap(False)
        key_error.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        key_error.hide()
        self._key_error_labels[provider_id] = key_error
        key_input.textChanged.connect(
            lambda _text="", current_provider=provider_id:
                self._validate_key_input(current_provider)
        )

        add_key = QPushButton("Додати ключ")
        add_key.clicked.connect(lambda: self._add_key(provider_id))
        key_row.addWidget(add_key)
        remove_key = QPushButton("Видалити вибраний")
        remove_key.clicked.connect(lambda: self._remove_key(provider_id))
        key_row.addWidget(remove_key)
        layout.addRow(key_row)
        layout.addRow(key_error)

        test_row = QHBoxLayout()
        test_button = QPushButton("Перевірити підключення")
        test_button.setObjectName(f"llmTest_{provider_id}")
        test_button.clicked.connect(lambda: self._test_provider(provider_id))
        test_row.addStretch(1)
        test_row.addWidget(test_button)
        layout.addRow(test_row)

        status = QLabel()
        status.setObjectName(f"llmProviderStatusText_{provider_id}")
        status.setWordWrap(True)
        status.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        layout.addRow(status)

        self._provider_groups[provider_id] = group
        self._provider_editor.addWidget(group)

    def _add_provider(self) -> None:
        dialog = AddProviderDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.provider_config is None:
            return

        provider_id = f"custom_{uuid4().hex}"
        self._preferences["providers"][provider_id] = dialog.provider_config
        self._credentials[provider_id] = []
        self._add_provider_order_item(provider_id)
        self._add_provider_group(provider_id, dialog.provider_config)
        self._mark_dirty()
        self._provider_order.setCurrentRow(self._provider_order.count() - 1)

    def _restore_default_providers(self) -> None:
        restored_ids = []
        for provider_id, provider_spec in DEFAULT_PROVIDERS.items():
            if provider_id in self._preferences["providers"]:
                continue
            config: ProviderSettings = {
                "name": provider_spec["name"],
                "type": provider_spec["type"],
                "api_url": provider_spec["api_url"],
                "model": provider_spec["model"],
            }
            self._preferences["providers"][provider_id] = config
            self._preferences["provider_order"].append(provider_id)
            self._credentials.setdefault(provider_id, [])
            self._add_provider_order_item(provider_id)
            self._add_provider_group(provider_id, config)
            restored_ids.append(provider_id)

        self._update_restore_defaults_button()
        if not restored_ids:
            return
        self._mark_dirty()
        self._provider_order.setCurrentRow(self._provider_order.count() - 1)

    def _update_restore_defaults_button(self) -> None:
        self._restore_defaults_button.setEnabled(
            any(
                provider_id not in self._preferences["providers"]
                for provider_id in DEFAULT_PROVIDERS
            )
        )

    def _remove_provider(self) -> None:
        item = self._provider_order.currentItem()
        if item is None:
            return
        provider_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(provider_id, str) or provider_id not in self._preferences["providers"]:
            return
        confirmation = QMessageBox.question(
            self,
            "Видалити провайдера",
            "Буде видалено налаштування провайдера та його ключі. Продовжити?",
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        del self._preferences["providers"][provider_id]
        self._provider_cards.pop(provider_id, None)
        item_index = self._provider_order.row(item)
        if item_index >= 0:
            self._provider_order.takeItem(item_index)
        if provider_id in self._preferences["provider_order"]:
            self._preferences["provider_order"].remove(provider_id)
        self._credentials.pop(provider_id, None)
        self._model_fields.pop(provider_id, None)
        self._key_lists.pop(provider_id, None)
        self._key_inputs.pop(provider_id, None)
        self._custom_fields.pop(provider_id, None)
        self._key_error_labels.pop(provider_id, None)
        group = self._provider_groups.pop(provider_id)
        if group is not None:
            self._provider_editor.removeWidget(group)
            group.hide()
            group.setParent(None)

        remaining_row = min(item_index, self._provider_order.count() - 1)
        if remaining_row >= 0:
            self._provider_order.setCurrentRow(remaining_row)
            self._select_provider(remaining_row)
        else:
            self._provider_editor.setCurrentWidget(
                self._provider_editor_empty
            )
            self._provider_editor_empty.show()

        self._renumber_provider_cards()
        self._update_restore_defaults_button()
        self._mark_dirty()

    def _refresh_key_list(self, provider_id: str) -> None:
        key_list = self._key_lists[provider_id]
        key_list.clear()
        for index, key in enumerate(self._credentials.get(provider_id, []), start=1):
            masked = f"Ключ {index}: ..." + key[-4:] if len(key) >= 4 else f"Ключ {index}: ****"
            key_list.addItem(masked)

    def _validate_key_input(self, provider_id: str) -> str | None:
        key_input = self._key_inputs.get(provider_id)
        error_label = self._key_error_labels.get(provider_id)
        if key_input is None or error_label is None:
            return None

        key = key_input.text().strip()
        if not key:
            key_input.setProperty("invalid", False)
            key_input.style().unpolish(key_input)
            key_input.style().polish(key_input)
            error_label.hide()
            error_label.clear()
            return None

        provider_spec = self._preferences["providers"].get(provider_id, {})
        error = validate_api_key(
            provider_id,
            key,
            provider_spec.get("type", ""),
            provider_spec.get("api_url", ""),
        )
        if error is None and key in self._credentials.get(provider_id, []):
            error = "Цей API-ключ уже додано."

        invalid = error is not None
        key_input.setProperty("invalid", invalid)
        key_input.style().unpolish(key_input)
        key_input.style().polish(key_input)
        if invalid:
            error_label.setText(error)
            error_label.show()
        else:
            error_label.hide()
            error_label.clear()
        return error

    def _set_key_error(self, provider_id: str, message: str) -> None:
        key_input = self._key_inputs.get(provider_id)
        error_label = self._key_error_labels.get(provider_id)
        if key_input is not None:
            key_input.setProperty("invalid", True)
            key_input.style().unpolish(key_input)
            key_input.style().polish(key_input)
        if error_label is not None:
            error_label.setText(message)
            error_label.show()

    def _clear_key_error(self, provider_id: str) -> None:
        key_input = self._key_inputs.get(provider_id)
        error_label = self._key_error_labels.get(provider_id)
        if key_input is not None:
            key_input.setProperty("invalid", False)
            key_input.style().unpolish(key_input)
            key_input.style().polish(key_input)
        if error_label is not None:
            error_label.clear()
            error_label.hide()

    def _add_key(self, provider_id: str) -> None:
        key_input = self._key_inputs[provider_id]
        key = key_input.text().strip()
        if not key:
            self._set_key_error(provider_id, "Введіть API-ключ.")
            return
        provider_spec = self._preferences["providers"].get(provider_id, {})
        key_error = validate_api_key(
            provider_id,
            key,
            provider_spec.get("type", ""),
            provider_spec.get("api_url", ""),
        )
        if key_error:
            self._set_key_error(provider_id, key_error)
            return
        provider_keys = self._credentials.setdefault(provider_id, [])
        if key in provider_keys:
            self._set_key_error(provider_id, "Цей API-ключ уже додано.")
            return
        provider_keys.append(key)
        self._refresh_key_list(provider_id)
        self._mark_dirty()
        self._refresh_provider_statuses()
        self._clear_key_error(provider_id)
        key_input.clear()

    def _remove_key(self, provider_id: str) -> None:
        key_list = self._key_lists[provider_id]
        selected_row = key_list.currentRow()
        provider_keys = self._credentials.get(provider_id, [])
        if 0 <= selected_row < len(provider_keys):
            del provider_keys[selected_row]
            self._refresh_key_list(provider_id)
            self._mark_dirty()
            self._refresh_provider_statuses()

    def _move_provider(self, offset: int) -> None:
        current_row = self._provider_order.currentRow()
        target_row = current_row + offset
        if current_row < 0 or not 0 <= target_row < self._provider_order.count():
            return
        provider_order = [
            self._provider_order.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self._provider_order.count())
            if self._provider_order.item(row) is not None
        ]
        provider_order[current_row], provider_order[target_row] = (
            provider_order[target_row],
            provider_order[current_row],
        )
        self._preferences["provider_order"] = provider_order
        self._provider_cards.clear()
        self._provider_order.clear()
        for provider_id in provider_order:
            self._add_provider_order_item(provider_id)
        self._provider_order.setCurrentRow(target_row)
        self._renumber_provider_cards()
        self._select_provider(target_row)
        self._mark_dirty()

    def _select_provider(self, row: int) -> None:
        if row < 0:
            return
        item = self._provider_order.item(row)
        if item is None:
            return
        provider_id = item.data(Qt.ItemDataRole.UserRole)
        group = self._provider_groups.get(provider_id)
        if group is not None:
            group.show()
            self._provider_editor.setCurrentWidget(group)
            self._provider_editor.show()
        for index in range(self._provider_order.count()):
            card_item = self._provider_order.item(index)
            if card_item is None:
                continue
            card = self._provider_order.itemWidget(card_item)
            if card is not None:
                card.setProperty("selected", card_item is item)
                card.style().unpolish(card)
                card.style().polish(card)

    def _renumber_provider_cards(self) -> None:
        for row in range(self._provider_order.count()):
            item = self._provider_order.item(row)
            if item is None:
                continue
            card = self._provider_order.itemWidget(item)
            if card is None:
                continue
            number = card.findChild(QLabel, "llmProviderNumber")
            if number is not None:
                number.setText(str(row + 1))

    def _refresh_provider_statuses(self) -> None:
        statuses = llm_client.get_router_statuses()
        ready_count = 0
        cooldown_seconds: list[int] = []
        deleted_provider_ids: list[str] = []
        for provider_id in list(self._preferences["provider_order"]):
            entry = self._provider_cards.get(provider_id)
            if entry is None:
                continue
            try:
                card, status, keys = entry
                if sip.isdeleted(card) or sip.isdeleted(status) or sip.isdeleted(keys):
                    deleted_provider_ids.append(provider_id)
                    continue
                credential_count = len(self._credentials.get(provider_id, []))
                keys.setText(
                    f"{credential_count} ключ{'і' if credential_count == 1 else 'ів'}"
                )
                state = statuses.get(provider_id, {}).get("state", "missing")
                seconds = statuses.get(provider_id, {}).get("seconds", 0)
                status.setObjectName("llmProviderStatusReady")
                if state == "ready":
                    status.setText("Готовий")
                    ready_count += 1
                elif state == "missing":
                    status.setText("Немає ключа")
                    status.setObjectName("llmProviderStatusMissing")
                elif state == "invalid":
                    status.setText("Недійсний ключ")
                    status.setObjectName("llmProviderStatusCooldown")
                elif state == "partial":
                    status.setText(f"Недійсний ключів: {seconds}")
                    status.setObjectName("llmProviderStatusCooldown")
                else:
                    status.setText(f"Відкладено, {seconds} c")
                    status.setObjectName("llmProviderStatusCooldown")
                    if isinstance(seconds, int):
                        cooldown_seconds.append(seconds)
                status.style().unpolish(status)
                status.style().polish(status)
            except RuntimeError:
                deleted_provider_ids.append(provider_id)
        for provider_id in deleted_provider_ids:
            self._provider_cards.pop(provider_id, None)
        if ready_count == 0 and cooldown_seconds:
            retry_seconds = min(cooldown_seconds)
            self._availability_banner.setText(
                "Усі провайдери тимчасово недоступні. "
                f"Наступна спроба приблизно через {retry_seconds} с."
            )
            self._availability_banner.show()
        else:
            self._availability_banner.hide()

    def _test_provider(self, provider_id: str) -> None:
        keys = self._credentials.get(provider_id, [])
        if not keys:
            self._set_provider_test_status(provider_id, "Немає ключа.")
            return
        provider_spec = self._preferences["providers"].get(provider_id)
        if provider_spec is None:
            return
        provider_spec = dict(provider_spec)
        model_field = self._model_fields.get(provider_id)
        if model_field is not None:
            provider_spec["model"] = model_field.text().strip()
        try:
            llm_client._request_provider(provider_spec, keys[0], "Скажи «Готово».")
        except llm_client._LLMRequestError as error:
            self._set_provider_test_status(provider_id, str(error))
            return
        self._set_provider_test_status(provider_id, "Підключення успішне.")
        self._refresh_provider_statuses()

    def _set_provider_test_status(self, provider_id: str, message: str) -> None:
        status = self.findChild(QLabel, f"llmProviderStatusText_{provider_id}")
        if status is not None:
            status.setText(message)

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
        for provider_id, fields in self._custom_fields.items():
            name_field = fields.get("name")
            type_field = fields.get("type")
            url_field = fields.get("url")
            if not isinstance(name_field, QLineEdit) or not isinstance(type_field, QComboBox) or not isinstance(url_field, QLineEdit):
                continue
            provider_type = type_field.currentData()
            try:
                api_url = (
                    normalize_anthropic_api_url(url_field.text())
                    if provider_type == "anthropic"
                    else normalize_openai_api_url(url_field.text())
                )
            except LLMConfigError as error:
                QMessageBox.critical(self, "Некоректна адреса API", str(error))
                return
            if not name_field.text().strip():
                QMessageBox.critical(
                    self,
                    "Не вдалося зберегти",
                    "Вкажіть назву провайдера.",
                )
                return
            providers[provider_id] = {
                **providers[provider_id],
                "name": name_field.text().strip(),
                "type": provider_type,
                "api_url": api_url,
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
        for provider_id, keys in credentials.items():
            provider_spec = providers[provider_id]
            for key in keys:
                key_error = validate_api_key(
                    provider_id,
                    key,
                    provider_spec["type"],
                    provider_spec["api_url"],
                )
                if key_error:
                    self._set_key_error(provider_id, key_error)
                    for row in range(self._provider_order.count()):
                        item = self._provider_order.item(row)
                        if item is not None and item.data(Qt.ItemDataRole.UserRole) == provider_id:
                            self._provider_order.setCurrentRow(row)
                            break
                    return
        try:
            save_credentials(credentials)
            save_preferences(preferences)
        except LLMConfigError as error:
            QMessageBox.critical(self, "Не вдалося зберегти", str(error))
            return
        self._save_status.setObjectName("llmSaveStatus")
        self._save_status.setText("Налаштування збережено.")
        self._dirty = False
        self.saved.emit()

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._save_status.setObjectName("llmUnsavedStatus")
        self._save_status.setText("Є незбережені зміни")
        self._save_status.style().unpolish(self._save_status)
        self._save_status.style().polish(self._save_status)

    def _back(self) -> None:
        if self._dirty:
            result = QMessageBox.question(
                self,
                "Незбережені зміни",
                "Є незбережені зміни. Повернутися до чату?",
            )
            if result != QMessageBox.StandardButton.Yes:
                return
        self.back_requested.emit()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._status_timer.stop()
        super().closeEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_provider_statuses()
        self._status_timer.start()

    def hideEvent(self, event: QHideEvent) -> None:
        self._status_timer.stop()
        super().hideEvent(event)
