import contextlib
import io
import json
import logging
import threading

from django.core.exceptions import BadRequest
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from core.management.commands.run_assistant import Command
from utils.voicing_answer import GUI_TEXT_MODE


logger = logging.getLogger(__name__)
_command_lock = threading.Lock()
_command: Command | None = None


def _get_command() -> Command:
    global _command
    with _command_lock:
        if _command is None:
            _command = Command()
            _command.initialize_for_text()
    return _command


@require_GET
def assistant_health(_request: HttpRequest) -> JsonResponse:
    try:
        _get_command()
        return JsonResponse({"ok": True, "status": "ready"})
    except Exception as error:
        logger.warning("Assistant backend initialization failed: %s", type(error).__name__)
        return JsonResponse(
            {"ok": False, "status": "error", "message": "Асистент не зміг ініціалізуватися."},
            status=503,
        )


@csrf_exempt
@require_POST
def assistant_command(request: HttpRequest) -> JsonResponse:
    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise BadRequest("Invalid JSON")

    text = str(payload.get("text", "")).strip()
    if not text:
        return JsonResponse({"ok": True, "output": ""})

    speak_answer = bool(payload.get("speak_answer", False))
    buffer = io.StringIO()

    try:
        command = _get_command()
        with _command_lock:
            from django.core.management.base import OutputWrapper
            command.stdout = OutputWrapper(buffer)

            if speak_answer:
                GUI_TEXT_MODE.clear()
            else:
                GUI_TEXT_MODE.set()

            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                command.process_recognized_command(text)

        output = buffer.getvalue().strip()
        lines = [
            line.strip()
            for line in output.splitlines()
            if line.strip() and not line.strip().startswith("Ви сказали:")
        ]
        return JsonResponse({"ok": True, "output": "\n".join(lines)})
    except Exception as error:
        logger.warning("Assistant command failed: %s", type(error).__name__)
        return JsonResponse(
            {
                "ok": False,
                "message": "Команду не вдалося виконати. Спробуйте ще раз.",
            },
            status=500,
        )
    finally:
        GUI_TEXT_MODE.clear()
