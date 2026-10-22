import asyncio
import os
import queue
import tempfile
import threading
import time

import edge_tts
import pygame

VOICE = "uk-UA-PolinaNeural"
VOICE = "uk-UA-PolinaNeural"

voice_profile = {
    "voice": VOICE,
    "rate": "-4%",
    "pitch": "-2Hz",
    "volume": "+0%",
}

VOICE_QUEUE: queue.Queue[tuple[str, int] | None] = queue.Queue()
MIXER_LOCK = threading.Lock()
AUDIO_LOCK = threading.Lock()
VOICE_ACTIVE = threading.Event()
VOICE_STATE_LOCK = threading.Lock()
_active_voice_requests = 0
_voice_generation = 0


def _mark_voice_request_started():
    global _active_voice_requests
    with VOICE_STATE_LOCK:
        _active_voice_requests += 1
        VOICE_ACTIVE.set()


def _mark_voice_request_finished():
    global _active_voice_requests
    with VOICE_STATE_LOCK:
        _active_voice_requests -= 1
        if _active_voice_requests == 0:
            VOICE_ACTIVE.clear()


def _is_current_voice_generation(generation: int) -> bool:
    with VOICE_STATE_LOCK:
        return generation == _voice_generation


def _voice_worker():
    while True:
        request = VOICE_QUEUE.get()
        if request is None:
            VOICE_QUEUE.task_done()
            break
        text, generation = request
        try:
            if _is_current_voice_generation(generation):
                with AUDIO_LOCK:
                    voicing_text(text, generation)
                    time.sleep(0.1)
        finally:
            VOICE_QUEUE.task_done()
            _mark_voice_request_finished()


async def create_voice(text: str, file_name: str):
    ready_voice = edge_tts.Communicate(
        text=text,
        voice=voice_profile["voice"],
        rate=voice_profile["rate"],
        pitch=voice_profile["pitch"],
        volume=voice_profile["volume"],
    )

    await ready_voice.save(audio_fname=file_name)


def voicing_text(text: str, generation: int | None = None):
    file_descriptor, file_name = tempfile.mkstemp(suffix=".mp3", prefix="voice_")
    os.close(file_descriptor)

    try:
        voicing_event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(voicing_event_loop)
        try:
            voicing_event_loop.run_until_complete(create_voice(text=text, file_name=file_name))
        finally:
            voicing_event_loop.close()
            asyncio.set_event_loop(None)

        if (
            os.path.exists(file_name)
            and os.path.getsize(file_name) > 0
            and (
                generation is None
                or _is_current_voice_generation(generation)
            )
        ):
            with MIXER_LOCK:
                if not pygame.get_init() or not pygame.mixer.get_init():
                    pygame.mixer.init()

                sound = pygame.mixer.Sound(file_name)
                with VOICE_STATE_LOCK:
                    if generation is not None and generation != _voice_generation:
                        return
                    channel = sound.play()

            try:
                while (
                    channel is not None
                    and channel.get_busy()
                    and (
                        generation is None
                        or _is_current_voice_generation(generation)
                    )
                ):
                    time.sleep(0.1)
            finally:
                sound.stop()
                del sound

    except Exception as e:
        print(f"Error playing file: {e}")

    finally:
        for attempt in range(10):
            try:
                if os.path.exists(file_name):
                    os.remove(file_name)
                break
            except PermissionError:
                time.sleep(0.1)
            except FileNotFoundError:
                break


_voice_thread = threading.Thread(target=_voice_worker, daemon=True)
_voice_thread.start()


def run_voice(text: str, wait: bool = False):
    if not text or not text.strip():
        return

    if wait:
        _mark_voice_request_started()
        with VOICE_STATE_LOCK:
            generation = _voice_generation
        try:
            with AUDIO_LOCK:
                voicing_text(text, generation)
                time.sleep(0.1)
        finally:
            _mark_voice_request_finished()
        return

    _mark_voice_request_started()
    try:
        with VOICE_STATE_LOCK:
            generation = _voice_generation
        VOICE_QUEUE.put((text, generation))
    except Exception:
        _mark_voice_request_finished()
        raise


def interrupt_voice() -> None:
    global _voice_generation
    with VOICE_STATE_LOCK:
        _voice_generation += 1

    while True:
        try:
            request = VOICE_QUEUE.get_nowait()
        except queue.Empty:
            break
        else:
            VOICE_QUEUE.task_done()
            if request is not None:
                _mark_voice_request_finished()

    with MIXER_LOCK:
        if pygame.mixer.get_init():
            pygame.mixer.stop()


def voicing_and_printing_answer(text: str):
    run_voice(text)
    print(text)