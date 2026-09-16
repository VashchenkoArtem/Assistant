import asyncio
import os
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

pygame.mixer.init()

async def create_voice(text: str, file_name: str):
    ready_voice = edge_tts.Communicate(
        text= text,
        voice= voice_profile["voice"],
        rate= voice_profile["rate"],
        pitch= voice_profile["pitch"],
        volume= voice_profile["volume"],
    )

    await ready_voice.save(audio_fname=file_name)


def voicing_text(text: str):
    file_name = f"voice_temp_{threading.get_ident()}_{time.time()}.mp3"
    try:
        voicing_event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(voicing_event_loop)

        voicing_event_loop.run_until_complete(create_voice(text=text, file_name=file_name))
        voicing_event_loop.close()

        if os.path.exists(file_name) and os.path.getsize(file_name) > 0:
            pygame.mixer.music.load(filename=file_name)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.2)
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()

    except Exception as e:
        print(f"Error playing file: {e}")

    finally:
        for trying in range(5):
            try:
                os.remove(file_name)
                break
            except PermissionError:
                time.sleep(0.1)


def run_voice(text: str):
    if not text or not text.strip():
        return

    voicing_thread = threading.Thread(target=voicing_text, args=(text,), daemon=True)
    voicing_thread.start()
