import asyncio
import os
import queue
import tempfile
import threading
import time

import edge_tts
import pygame

VOICE = "uk-UA-PolinaNeural"

voice_profile = {
    "voice": VOICE,
    "rate": "-4%",
    "pitch": "-2Hz",
    "volume": "+0%",
}

VOICE_QUEUE = queue.Queue()
MIXER_LOCK = threading.Lock()


def _voice_worker():
    while True:
        text = VOICE_QUEUE.get()
        if text is None:
            VOICE_QUEUE.task_done()
            break
        try:
            voicing_text(text)
        finally:
            VOICE_QUEUE.task_done()


async def create_voice(text: str, file_name: str):
    ready_voice = edge_tts.Communicate(
        text=text,
        voice=voice_profile["voice"],
        rate=voice_profile["rate"],
        pitch=voice_profile["pitch"],
        volume=voice_profile["volume"],
    )

    await ready_voice.save(audio_fname=file_name)


def voicing_text(text: str):
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

        if os.path.exists(file_name) and os.path.getsize(file_name) > 0:
            with MIXER_LOCK:
                if not pygame.get_init() or not pygame.mixer.get_init():
                    pygame.mixer.init()

                sound = pygame.mixer.Sound(file_name)
                channel = sound.play()

                try:
                    while channel is not None and channel.get_busy():
                        time.sleep(0.1)
                finally:
                    try:
                        sound.stop()
                    except Exception:
                        pass
                    del sound
                    pygame.mixer.stop()

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
        voicing_text(text)
        return

    VOICE_QUEUE.put(text)
