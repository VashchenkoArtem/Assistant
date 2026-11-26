import threading

from PyQt6.QtCore import QSettings


ORGANIZATION_NAME = "VashchenkoArtem"
APPLICATION_NAME = "Assistant"
MIXER_LOCK = threading.Lock()
MICROPHONE_DEVICE_KEY = "audio/microphone_device_index"
OUTPUT_DEVICE_KEY = "audio/output_device_name"
OUTPUT_VOLUME_KEY = "audio/output_volume_percent"


def _settings() -> QSettings:
    return QSettings(ORGANIZATION_NAME, APPLICATION_NAME)


def get_microphone_device_index() -> int:
    return _settings().value(MICROPHONE_DEVICE_KEY, -1, type=int)


def get_output_device_name() -> str:
    return _settings().value(OUTPUT_DEVICE_KEY, "", type=str)


def get_output_volume() -> float:
    volume_percent = _settings().value(OUTPUT_VOLUME_KEY, 100, type=int)
    return max(0, min(100, volume_percent)) / 100


def save_audio_settings(
    microphone_device_index: int,
    output_device_name: str,
    output_volume_percent: int,
) -> None:
    if microphone_device_index < -1:
        raise ValueError("Індекс мікрофона має бути -1 або невід’ємним.")
    if not 0 <= output_volume_percent <= 100:
        raise ValueError("Гучність має бути від 0 до 100.")

    settings = _settings()
    settings.setValue(MICROPHONE_DEVICE_KEY, microphone_device_index)
    settings.setValue(OUTPUT_DEVICE_KEY, output_device_name)
    settings.setValue(OUTPUT_VOLUME_KEY, output_volume_percent)
    settings.sync()
    if settings.status() != QSettings.Status.NoError:
        raise OSError("Не вдалося зберегти налаштування звуку.")


def list_microphone_devices() -> list[tuple[int, str]]:
    import speech_recognition

    return list(enumerate(speech_recognition.Microphone.list_microphone_names()))


def list_output_devices() -> list[str]:
    import pygame
    from pygame._sdl2 import audio

    with MIXER_LOCK:
        mixer_was_initialized = pygame.mixer.get_init() is not None
        try:
            if not mixer_was_initialized:
                pygame.mixer.init()
            return audio.get_audio_device_names(False)
        except pygame.error as error:
            raise RuntimeError(
                f"Не вдалося отримати список аудіопристроїв: {error}"
            ) from error
        finally:
            if not mixer_was_initialized and pygame.mixer.get_init() is not None:
                pygame.mixer.quit()
