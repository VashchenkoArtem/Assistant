import sys
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


def resolve_microphone_device_index() -> int | None:
    selected_index = get_microphone_device_index()
    if selected_index < 0:
        return None
    available_indexes = {index for index, _name in list_microphone_devices()}
    return selected_index if selected_index in available_indexes else None


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


def _repair_microphone_name(name: str) -> str:
    try:
        return name.encode("cp1251").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def _normalize_microphone_name(name: str) -> str:
    return " ".join(_repair_microphone_name(name).casefold().split())


def _list_active_windows_microphone_names() -> set[str]:
    from _ctypes import COMError

    import comtypes
    from pycaw.constants import DEVICE_STATE, EDataFlow
    from pycaw.pycaw import AudioUtilities

    initialized = False
    try:
        comtypes.CoInitialize()
        initialized = True
        devices = AudioUtilities.GetAllDevices(
            data_flow=EDataFlow.eCapture.value,
            device_state=DEVICE_STATE.ACTIVE.value,
        )
        names = set()
        for device in devices:
            name = device.FriendlyName
            if isinstance(name, str) and name.strip():
                names.add(_normalize_microphone_name(name))
    except (COMError, OSError) as error:
        raise RuntimeError(
            f"Не вдалося отримати активні мікрофони Windows: {error}"
        ) from error
    finally:
        if initialized:
            comtypes.CoUninitialize()
    return names


def list_microphone_devices() -> list[tuple[int, str]]:
    import speech_recognition

    active_names = (
        _list_active_windows_microphone_names()
        if sys.platform == "win32"
        else None
    )
    pyaudio = speech_recognition.Microphone.get_pyaudio()
    audio = pyaudio.PyAudio()
    try:
        devices = []
        seen_names = set()
        for index in range(audio.get_device_count()):
            device_info = audio.get_device_info_by_index(index)
            name = device_info["name"]
            max_input_channels = device_info["maxInputChannels"]
            if not isinstance(name, str) or not isinstance(
                max_input_channels, (int, float)
            ):
                raise RuntimeError(
                    f"Отримано некоректні дані для аудіопристрою {index}."
                )
            if max_input_channels <= 0:
                continue
            repaired_name = _repair_microphone_name(name)
            normalized_name = _normalize_microphone_name(repaired_name)
            if active_names is not None:
                if (
                    normalized_name not in active_names
                    or normalized_name in seen_names
                ):
                    continue
                seen_names.add(normalized_name)
            devices.append((index, repaired_name))
        return devices
    finally:
        audio.terminate()


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
