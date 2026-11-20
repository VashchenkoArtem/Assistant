import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import urlsplit, urlunsplit


ROOT_DIR = Path(__file__).resolve().parents[1]
CREDENTIALS_FILE = ROOT_DIR / ".llm_credentials.json"
PREFERENCES_FILE = ROOT_DIR / ".llm_preferences.json"

DEFAULT_PROVIDERS = {
    "groq": {
        "name": "Groq",
        "type": "openai_compatible",
        "api_url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
    },
    "gemini": {
        "name": "Google Gemini",
        "type": "gemini",
        "api_url": "",
        "model": "gemini-2.5-flash",
    },
}
DEFAULT_PROVIDER_ORDER = tuple(DEFAULT_PROVIDERS)
DEFAULT_PREFERENCES = {
    "fallback_enabled": True,
    "provider_order": list(DEFAULT_PROVIDER_ORDER),
    "providers": DEFAULT_PROVIDERS,
}
PROVIDER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SUPPORTED_PROVIDER_TYPES = {"anthropic", "gemini", "openai_compatible"}


class LLMConfigError(ValueError):
    """Raised when locally stored LLM settings cannot be read or written."""


class ProviderSettings(TypedDict):
    name: str
    type: str
    api_url: str
    model: str


class LLMPreferences(TypedDict):
    fallback_enabled: bool
    provider_order: list[str]
    providers: dict[str, ProviderSettings]


def normalize_openai_api_url(url: str) -> str:
    try:
        parsed = urlsplit(url.strip())
    except ValueError as error:
        raise LLMConfigError("Вкажіть коректну URL-адресу API.") from error
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise LLMConfigError("Вкажіть коректну URL-адресу API.")
    if parsed.scheme != "https" and parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise LLMConfigError("Для зовнішніх API потрібне захищене HTTPS-з'єднання.")

    path = parsed.path.rstrip("/")
    if not path.endswith("/chat/completions"):
        path += "/chat/completions" if path.endswith("/v1") else "/v1/chat/completions"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def normalize_anthropic_api_url(url: str) -> str:
    try:
        parsed = urlsplit(url.strip())
    except ValueError as error:
        raise LLMConfigError("Вкажіть коректну URL-адресу API.") from error
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise LLMConfigError("Вкажіть коректну URL-адресу API.")
    if parsed.scheme != "https" and parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise LLMConfigError("Для зовнішніх API потрібне захищене HTTPS-з'єднання.")

    path = parsed.path.rstrip("/")
    if not path.endswith("/v1/messages"):
        path += "/messages" if path.endswith("/v1") else "/v1/messages"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LLMConfigError(
            f"Не вдалося прочитати файл налаштувань {path.name}."
        ) from error


def _write_json_atomically(path: Path, data: object) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(data, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
        os.replace(temporary_path, path)
    except OSError as error:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                error.add_note(
                    f"Тимчасовий файл {temporary_path.name} не вдалося видалити."
                )
        raise LLMConfigError(
            f"Не вдалося зберегти файл налаштувань {path.name}."
        ) from error


def _is_valid_provider_id(provider: object) -> bool:
    return isinstance(provider, str) and PROVIDER_ID_PATTERN.fullmatch(provider) is not None


def load_credentials() -> dict[str, list[str]]:
    if not CREDENTIALS_FILE.exists():
        return {}
    data = _read_json(CREDENTIALS_FILE)
    if not isinstance(data, dict):
        raise LLMConfigError("Файл ключів LLM має некоректний формат.")

    credentials: dict[str, list[str]] = {}
    for provider, keys in data.items():
        if not _is_valid_provider_id(provider):
            raise LLMConfigError("Файл ключів містить некоректний ідентифікатор.")
        if not isinstance(keys, list) or any(
            not isinstance(key, str) or not key.strip() for key in keys
        ):
            raise LLMConfigError("Файл ключів LLM має некоректний формат.")
        credentials[provider] = list(dict.fromkeys(key.strip() for key in keys))
    return credentials


def save_credentials(credentials: dict[str, list[str]]) -> None:
    normalized: dict[str, list[str]] = {}
    for provider, keys in credentials.items():
        if not _is_valid_provider_id(provider):
            raise LLMConfigError("Не можна зберегти ключ для некоректного провайдера.")
        if not isinstance(keys, list) or any(
            not isinstance(key, str) or not key.strip() for key in keys
        ):
            raise LLMConfigError("Ключі LLM не можуть бути порожніми.")
        normalized_keys = [key.strip() for key in keys]
        if any(any(character.isspace() for character in key) for key in normalized_keys):
            raise LLMConfigError(
                "API-ключ має бути одним рядком без пробілів і переносів."
            )
        normalized[provider] = list(dict.fromkeys(normalized_keys))
    _write_json_atomically(CREDENTIALS_FILE, normalized)


def _validated_provider(provider: object) -> ProviderSettings:
    if not isinstance(provider, dict):
        raise LLMConfigError("Параметри провайдера мають некоректний формат.")
    name = provider.get("name")
    provider_type = provider.get("type")
    model = provider.get("model")
    api_url = provider.get("api_url", "")
    if (
        not isinstance(name, str)
        or not name.strip()
        or not isinstance(provider_type, str)
        or provider_type not in SUPPORTED_PROVIDER_TYPES
        or not isinstance(model, str)
        or not model.strip()
        or not isinstance(api_url, str)
    ):
        raise LLMConfigError("Параметри провайдера мають некоректний формат.")
    if provider_type == "openai_compatible":
        api_url = normalize_openai_api_url(api_url)
    elif provider_type == "anthropic":
        api_url = normalize_anthropic_api_url(api_url)
    elif api_url:
        raise LLMConfigError("Gemini використовує вбудовану адресу API.")
    return ProviderSettings(
        name=name.strip(),
        type=provider_type,
        api_url=api_url,
        model=model.strip(),
    )


def load_preferences() -> LLMPreferences:
    if not PREFERENCES_FILE.exists():
        return {
            "fallback_enabled": True,
            "provider_order": list(DEFAULT_PROVIDER_ORDER),
            "providers": {
                provider: _validated_provider(config)
                for provider, config in DEFAULT_PROVIDERS.items()
            },
        }

    data = _read_json(PREFERENCES_FILE)
    if not isinstance(data, dict):
        raise LLMConfigError("Файл параметрів LLM має некоректний формат.")

    raw_providers = data.get("providers")
    if raw_providers is None:
        raw_providers = {
            provider: {
                **config,
                "model": data.get("models", {}).get(provider, config["model"])
                if isinstance(data.get("models", {}), dict)
                else config["model"],
            }
            for provider, config in DEFAULT_PROVIDERS.items()
        }
    if (
        not isinstance(raw_providers, dict)
        or not raw_providers
        or any(not _is_valid_provider_id(provider) for provider in raw_providers)
    ):
        raise LLMConfigError("Список провайдерів LLM має некоректний формат.")
    providers = {
        provider: _validated_provider(config)
        for provider, config in raw_providers.items()
    }

    provider_order = data.get("provider_order", list(providers))
    if (
        not isinstance(provider_order, list)
        or any(
            not isinstance(provider, str) or provider not in providers
            for provider in provider_order
        )
        or len(set(provider_order)) != len(provider_order)
        or set(provider_order) != set(providers)
    ):
        raise LLMConfigError("Порядок провайдерів LLM має некоректний формат.")
    fallback_enabled = data.get("fallback_enabled", True)
    if not isinstance(fallback_enabled, bool):
        raise LLMConfigError("Параметр резервного перемикання має бути так або ні.")
    return {
        "fallback_enabled": fallback_enabled,
        "provider_order": provider_order,
        "providers": providers,
    }


def save_preferences(preferences: dict[str, Any]) -> None:
    providers = preferences.get("providers")
    provider_order = preferences.get("provider_order")
    fallback_enabled = preferences.get("fallback_enabled")
    if (
        not isinstance(providers, dict)
        or not providers
        or any(not _is_valid_provider_id(provider) for provider in providers)
        or not isinstance(provider_order, list)
        or any(
            not isinstance(provider, str) or provider not in providers
            for provider in provider_order
        )
        or set(provider_order) != set(providers)
        or len(provider_order) != len(providers)
        or not isinstance(fallback_enabled, bool)
    ):
        raise LLMConfigError("Налаштування LLM мають некоректний формат.")

    validated_providers = {
        provider: _validated_provider(config)
        for provider, config in providers.items()
    }
    _write_json_atomically(
        PREFERENCES_FILE,
        {
            "fallback_enabled": fallback_enabled,
            "provider_order": provider_order,
            "providers": validated_providers,
        },
    )
