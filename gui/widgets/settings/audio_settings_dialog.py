from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from utils.audio_settings import (
    get_microphone_device_index,
    get_output_device_name,
    get_output_volume,
    list_microphone_devices,
    list_output_devices,
    save_audio_settings,
)


class AudioSettingsDialog(QWidget):
    back_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("audioSettingsPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(8)

        title = QLabel("Налаштування звуку")
        title.setObjectName("audioSettingsTitle")
        layout.addWidget(title)

        description = QLabel(
            "Мікрофон для розпізнавання голосу, пристрій для відтворення "
            "та гучність озвучення."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.microphone = QComboBox()
        self.microphone.setObjectName("audioMicrophoneDevice")
        self.output_device = QComboBox()
        self.output_device.setObjectName("audioOutputDevice")
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setObjectName("audioOutputVolume")
        self.volume.setRange(0, 100)
        self.volume.setValue(round(get_output_volume() * 100))
        self.volume_label = QLabel(f"{self.volume.value()}%")
        self.volume.valueChanged.connect(
            lambda value: self.volume_label.setText(f"{value}%")
        )
        settings_group = QGroupBox("Аудіопристрої")
        form = QFormLayout(settings_group)
        form.setContentsMargins(14, 14, 14, 14)
        form.setSpacing(10)
        form.addRow("Мікрофон", self.microphone)
        form.addRow("Вихідний пристрій", self.output_device)
        volume_row = QHBoxLayout()
        volume_row.addWidget(self.volume, 1)
        volume_row.addWidget(self.volume_label)
        form.addRow("Гучність", volume_row)
        layout.addWidget(settings_group)

        self.save_button = QPushButton("Зберегти")
        self.save_button.clicked.connect(self._save)
        close_button = QPushButton("Назад до чату")
        close_button.clicked.connect(self.back_requested.emit)
        buttons = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("audioSaveStatus")
        self.status.setWordWrap(True)
        buttons.addWidget(self.status, 1)
        buttons.addStretch(1)
        buttons.addWidget(self.save_button)
        buttons.addWidget(close_button)
        layout.addStretch(1)
        layout.addLayout(buttons)
        self._load_devices()

    def _load_devices(self) -> None:
        self.microphone.addItem("Системний за замовчуванням", -1)
        self.output_device.addItem("Системний за замовчуванням", "")

        errors: list[str] = []
        try:
            for index, name in list_microphone_devices():
                self.microphone.addItem(f"{name} ({index})", index)
        except (ImportError, OSError, RuntimeError) as error:
            errors.append(f"Не вдалося отримати мікрофони: {error}")
        try:
            for name in list_output_devices():
                self.output_device.addItem(name, name)
        except (ImportError, OSError, RuntimeError) as error:
            errors.append(f"Не вдалося отримати аудіовиходи: {error}")

        saved_microphone_index = get_microphone_device_index()
        microphone_index = self.microphone.findData(saved_microphone_index)
        if microphone_index >= 0:
            self.microphone.setCurrentIndex(microphone_index)
        elif saved_microphone_index >= 0:
            self.microphone.setCurrentIndex(0)
            errors.append(
                "Збережений мікрофон недоступний; вибрано системний за замовчуванням."
            )
        output_index = self.output_device.findData(get_output_device_name())
        if output_index >= 0:
            self.output_device.setCurrentIndex(output_index)
        if errors:
            self.status.setText("\n".join(errors))

    def _save(self) -> None:
        try:
            save_audio_settings(
                self.microphone.currentData(),
                self.output_device.currentData(),
                self.volume.value(),
            )
        except (OSError, ValueError) as error:
            self.status.setText(f"Не вдалося зберегти налаштування: {error}")
            return
        self.status.setText("Налаштування збережено.")
