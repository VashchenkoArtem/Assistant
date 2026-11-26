import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from math import ceil

from utils.llm_config import (
    DEFAULT_PROVIDERS,
    LLMConfigError,
    LLMPreferences,
    ProviderSettings,
    load_credentials,
    load_preferences,
)


API_TIMEOUT_SECONDS = 20
GROQ_API_URL = DEFAULT_PROVIDERS["groq"]["api_url"]
QUOTA_COOLDOWN_SECONDS = 90
PROVIDER_COOLDOWN_SECONDS = 45
INVALID_KEY_MESSAGE = "Помилка авторизації LLM API. Перевірте API-ключ."
RATE_LIMIT_MESSAGE = "Перевищено ліміт запитів LLM API (429)."
NETWORK_ERROR_MESSAGE = (
    "Не вдалося з'єднатися з LLM API. "
    "Перевірте інтернет-з'єднання та спробуйте ще раз."
)
INVALID_RESPONSE_MESSAGE = "LLM API повернув некоректну відповідь."
INVALID_KEY_FORMAT_MESSAGE = (
    "Некоректний формат API-ключа. Вставте лише сам ключ без пробілів, "
    "переносів рядків чи коду прикладу."
)
INVALID_REQUEST_MESSAGE = (
    "Не вдалося підготувати запит до LLM API. Перевірте формат ключа та URL."
)
_BEARER_TOKEN_PATTERN = re.compile(r"(?i)(Bearer\s+)[^\s,;\"']+")
SYSTEM_PROMPT = (
    "Ти Поліна, помічниця. Відповідай українською мовою, стисло та по суті."
)


class _LLMRequestError(Exception):
    def __init__(self, message: str, category: str) -> None:
        super().__init__(message)
        self.category = category


_ROUTER_LOCK = threading.RLock()
_ROUTER_FINGERPRINT: str | None = None
_KEY_COOLDOWNS: dict[tuple[str, str], float] = {}
_INVALID_KEYS: set[tuple[str, str]] = set()
_PROVIDER_COOLDOWNS: dict[str, float] = {}


def _environment_keys(provider_id: str) -> list[str]:
    if provider_id == "groq":
        names = ["LLM_API_KEY", "GROQ_API_KEY"]
        numbered_prefix = "GROQ_API_KEY_"
    elif provider_id == "gemini":
        names = ["GEMINI_API_KEY"]
        numbered_prefix = "GEMINI_API_KEY_"
    else:
        prefix = f"LLM_{provider_id.upper()}_API_KEY"
        names = [prefix]
        numbered_prefix = f"{prefix}_"
    keys = [
        value.strip()
        for name in names
        if (value := os.environ.get(name, "").strip())
    ]
    numbered_keys = []
    for name, value in os.environ.items():
        suffix = name.removeprefix(numbered_prefix)
        if (
            name.startswith(numbered_prefix)
            and suffix.isdigit()
            and int(suffix) >= 2
            and value.strip()
        ):
            numbered_keys.append((int(suffix), value.strip()))
    keys.extend(key for _index, key in sorted(numbered_keys))
    return keys


def _provider_keys(
    provider_id: str,
    credentials: dict[str, list[str]],
) -> list[str]:
    return list(
        dict.fromkeys(
            [*_environment_keys(provider_id), *credentials.get(provider_id, [])]
        )
    )


def _key_identity(provider_id: str, api_key: str) -> tuple[str, str]:
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    return provider_id, digest


def _refresh_router_state(
    preferences: LLMPreferences,
    provider_keys: dict[str, list[str]],
) -> None:
    global _ROUTER_FINGERPRINT
    fingerprint_data = json.dumps(
        {"preferences": preferences, "keys": provider_keys},
        sort_keys=True,
        ensure_ascii=True,
    ).encode("utf-8")
    fingerprint = hashlib.sha256(fingerprint_data).hexdigest()
    with _ROUTER_LOCK:
        if fingerprint != _ROUTER_FINGERPRINT:
            _KEY_COOLDOWNS.clear()
            _INVALID_KEYS.clear()
            _PROVIDER_COOLDOWNS.clear()
            _ROUTER_FINGERPRINT = fingerprint


def _available_candidates(
    preferences: LLMPreferences,
    provider_keys: dict[str, list[str]],
    now: float,
) -> tuple[list[tuple[str, ProviderSettings, str]], list[float], int]:
    providers = preferences["providers"]
    provider_order = preferences["provider_order"]
    fallback_enabled = preferences["fallback_enabled"]
    candidates: list[tuple[str, ProviderSettings, str]] = []
    cooldowns: list[float] = []
    invalid_key_count = 0

    if not fallback_enabled:
        for provider_id in provider_order:
            keys = provider_keys[provider_id]
            if not keys:
                continue
            with _ROUTER_LOCK:
                provider_cooldown = _PROVIDER_COOLDOWNS.get(provider_id, 0)
                if provider_cooldown > now:
                    return [], [provider_cooldown], 0
                if provider_cooldown:
                    _PROVIDER_COOLDOWNS.pop(provider_id, None)
                identity = _key_identity(provider_id, keys[0])
                if identity in _INVALID_KEYS:
                    return [], [], 1
                key_cooldown = _KEY_COOLDOWNS.get(identity, 0)
                if key_cooldown > now:
                    return [], [key_cooldown], 0
                if key_cooldown:
                    _KEY_COOLDOWNS.pop(identity, None)
                return [(provider_id, providers[provider_id], keys[0])], [], 0
        return [], [], 0

    with _ROUTER_LOCK:
        for provider_id in provider_order:
            spec = providers[provider_id]
            keys = provider_keys[provider_id]
            if not keys:
                continue
            provider_cooldown = _PROVIDER_COOLDOWNS.get(provider_id, 0)
            if provider_cooldown > now:
                cooldowns.append(provider_cooldown)
                continue
            if provider_cooldown:
                _PROVIDER_COOLDOWNS.pop(provider_id, None)

            for api_key in keys:
                identity = _key_identity(provider_id, api_key)
                if identity in _INVALID_KEYS:
                    invalid_key_count += 1
                    if not fallback_enabled:
                        return [], cooldowns, invalid_key_count
                    continue
                key_cooldown = _KEY_COOLDOWNS.get(identity, 0)
                if key_cooldown > now:
                    cooldowns.append(key_cooldown)
                    if not fallback_enabled:
                        return [], cooldowns, invalid_key_count
                    continue
                if key_cooldown:
                    _KEY_COOLDOWNS.pop(identity, None)

                candidates.append((provider_id, spec, api_key))
    return candidates, cooldowns, invalid_key_count


def _response_text(provider_type: str, data: object) -> str:
    if not isinstance(data, dict):
        raise _LLMRequestError(INVALID_RESPONSE_MESSAGE, "fatal")

    if provider_type == "gemini":
        candidates = data.get("candidates")
        if (
            not isinstance(candidates, list)
            or not candidates
            or not isinstance(candidates[0], dict)
        ):
            raise _LLMRequestError(INVALID_RESPONSE_MESSAGE, "fatal")
        content = candidates[0].get("content")
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            raise _LLMRequestError(INVALID_RESPONSE_MESSAGE, "fatal")
        text = "".join(
            part["text"]
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ).strip()
    elif provider_type == "anthropic":
        content = data.get("content")
        if not isinstance(content, list):
            raise _LLMRequestError(INVALID_RESPONSE_MESSAGE, "fatal")
        text = "".join(
            part["text"]
            for part in content
            if (
                isinstance(part, dict)
                and part.get("type") == "text"
                and isinstance(part.get("text"), str)
            )
        ).strip()
    else:
        choices = data.get("choices")
        if (
            not isinstance(choices, list)
            or not choices
            or not isinstance(choices[0], dict)
        ):
            raise _LLMRequestError(INVALID_RESPONSE_MESSAGE, "fatal")
        message = choices[0].get("message")
        content = message.get("content") if isinstance(message, dict) else None
        text = content.strip() if isinstance(content, str) else ""

    if not text:
        raise _LLMRequestError("LLM API повернув порожню відповідь.", "fatal")
    return text


def _http_error_detail(error: urllib.error.HTTPError, api_key: str) -> str:
    if error.fp is None:
        return ""
    try:
        response_body = error.read().decode("utf-8")
        payload = json.loads(response_body)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ""

    if not isinstance(payload, dict):
        return ""
    error_payload = payload.get("error")
    if isinstance(error_payload, dict):
        detail = error_payload.get("message") or error_payload.get("detail")
    elif isinstance(error_payload, str):
        detail = error_payload
    else:
        detail = payload.get("detail") or payload.get("message")
    if not isinstance(detail, str):
        return ""

    detail = _BEARER_TOKEN_PATTERN.sub(r"\1[приховано]", detail)
    if api_key:
        detail = detail.replace(api_key, "[ключ приховано]")
    return " ".join(detail.split())[:300]


def _request_provider(
    provider_spec: ProviderSettings,
    api_key: str,
    prompt: str,
) -> str:
    if not api_key or any(character.isspace() for character in api_key):
        raise _LLMRequestError(INVALID_KEY_FORMAT_MESSAGE, "invalid_key")

    provider_type = provider_spec["type"]
    model = provider_spec["model"]
    if provider_type == "gemini":
        encoded_model = urllib.parse.quote(model, safe="")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{encoded_model}:generateContent"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        }
        headers = {"x-goog-api-key": api_key}
    elif provider_type == "anthropic":
        url = provider_spec["api_url"]
        payload = {
            "model": model,
            "max_tokens": 1024,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    else:
        url = provider_spec["api_url"]
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
        if urllib.parse.urlsplit(url).hostname == "integrate.api.nvidia.com":
            payload.update(
                {
                    "max_tokens": 1024,
                    "temperature": 1.0,
                    "top_p": 0.95,
                    "stream": False,
                }
            )
        headers = {"Authorization": f"Bearer {api_key}"}

    try:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise _LLMRequestError(INVALID_KEY_MESSAGE, "invalid_key") from error
        if error.code == 429:
            raise _LLMRequestError(RATE_LIMIT_MESSAGE, "quota") from error
        if error.code == 408 or 500 <= error.code < 600:
            raise _LLMRequestError(
                f"Тимчасова помилка LLM API (HTTP {error.code}).",
                "transient",
            ) from error
        detail = _http_error_detail(error, api_key)
        message = f"Помилка LLM API (HTTP {error.code})."
        if detail:
            message = f"{message} {detail}"
        raise _LLMRequestError(
            message,
            "fatal",
        ) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise _LLMRequestError(NETWORK_ERROR_MESSAGE, "transient") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _LLMRequestError(INVALID_RESPONSE_MESSAGE, "fatal") from error
    except ValueError as error:
        raise _LLMRequestError(INVALID_REQUEST_MESSAGE, "fatal") from error
    return _response_text(provider_type, data)


def _request_with_retry(
    provider_spec: ProviderSettings,
    api_key: str,
    prompt: str,
) -> str:
    try:
        return _request_provider(provider_spec, api_key, prompt)
    except _LLMRequestError as first_error:
        if first_error.category != "transient":
            raise
    try:
        return _request_provider(provider_spec, api_key, prompt)
    except _LLMRequestError as retry_error:
        if retry_error.category == "transient":
            raise _LLMRequestError(
                str(retry_error),
                "provider_cooldown",
            ) from retry_error
        raise


def _record_key_cooldown(provider_id: str, api_key: str, now: float) -> None:
    with _ROUTER_LOCK:
        _KEY_COOLDOWNS[_key_identity(provider_id, api_key)] = (
            now + QUOTA_COOLDOWN_SECONDS
        )


def _record_invalid_key(provider_id: str, api_key: str) -> None:
    with _ROUTER_LOCK:
        _INVALID_KEYS.add(_key_identity(provider_id, api_key))


def _record_provider_cooldown(provider_id: str, now: float) -> None:
    with _ROUTER_LOCK:
        _PROVIDER_COOLDOWNS[provider_id] = now + PROVIDER_COOLDOWN_SECONDS


def _no_candidate_message(
    provider_keys: dict[str, list[str]],
    cooldowns: list[float],
    invalid_key_count: int,
    now: float,
) -> str:
    if cooldowns:
        retry_seconds = max(1, ceil(min(cooldowns) - now))
        return (
            "Усі доступні ключі або провайдери тимчасово на паузі. "
            f"Повторіть запит приблизно через {retry_seconds} с."
        )
    if invalid_key_count:
        return (
            "Усі доступні ключі позначені як недійсні. "
            "Оновіть ключ у персоналізації або перезапустіть асистента."
        )
    if not any(provider_keys.values()):
        return (
            "LLM не налаштовано: додайте API-ключі у вікні персоналізації "
            "або задайте їх у змінних середовища."
        )
    return INVALID_KEY_MESSAGE


def ask_llm(prompt: str) -> str:
    try:
        preferences = load_preferences()
        credentials = load_credentials()
    except LLMConfigError as error:
        return str(error)

    provider_keys = {
        provider_id: _provider_keys(provider_id, credentials)
        for provider_id in preferences["provider_order"]
    }
    _refresh_router_state(preferences, provider_keys)

    now = time.monotonic()
    candidates, cooldowns, invalid_key_count = _available_candidates(
        preferences,
        provider_keys,
        now,
    )
    if not candidates:
        return _no_candidate_message(
            provider_keys,
            cooldowns,
            invalid_key_count,
            now,
        )

    fallback_enabled = preferences["fallback_enabled"]
    last_error: str | None = None
    attempted_count = 0
    cooled_providers: set[str] = set()
    for provider_id, provider_spec, api_key in candidates:
        if provider_id in cooled_providers:
            continue
        attempted_count += 1
        try:
            return _request_with_retry(provider_spec, api_key, prompt)
        except _LLMRequestError as error:
            last_error = str(error)
            if error.category == "quota":
                _record_key_cooldown(provider_id, api_key, time.monotonic())
            elif error.category == "invalid_key":
                _record_invalid_key(provider_id, api_key)
            elif error.category == "provider_cooldown":
                _record_provider_cooldown(provider_id, time.monotonic())
                cooled_providers.add(provider_id)
            else:
                cooled_providers.add(provider_id)
            if not fallback_enabled:
                break

    if last_error is None:
        return INVALID_RESPONSE_MESSAGE
    if attempted_count > 1:
        return (
            "Не вдалося отримати відповідь від налаштованих моделей. "
            f"Остання помилка: {last_error}"
        )
    return last_error
