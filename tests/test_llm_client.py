import json
import io
import os
import urllib.error
from email.message import Message
from unittest.mock import Mock, patch

import pytest

from utils import llm_client, llm_config


@pytest.fixture(autouse=True)
def isolate_llm_configuration(monkeypatch, tmp_path):
    monkeypatch.setattr(llm_config, "CREDENTIALS_FILE", tmp_path / "keys.json")
    monkeypatch.setattr(llm_config, "PREFERENCES_FILE", tmp_path / "preferences.json")
    with llm_client._ROUTER_LOCK:
        llm_client._KEY_COOLDOWNS.clear()
        llm_client._INVALID_KEYS.clear()
        llm_client._PROVIDER_COOLDOWNS.clear()
        llm_client._ROUTER_FINGERPRINT = None
    for name in (
        "LLM_API_KEY",
        "LLM_MODEL",
        "GROQ_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_MODEL",
        "GEMINI_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    for name in tuple(os.environ):
        if name.startswith(("GROQ_API_KEY_", "GEMINI_API_KEY_")):
            monkeypatch.delenv(name, raising=False)


def make_response(data):
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = json.dumps(data).encode("utf-8")
    return response


def default_providers():
    return {
        provider_id: dict(config)
        for provider_id, config in llm_config.DEFAULT_PROVIDERS.items()
    }


def test_ask_llm_sends_prompt_and_returns_response(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    response = make_response(
        {"choices": [{"message": {"content": "  Відповідь українською  "}}]}
    )

    with patch.object(llm_client.urllib.request, "urlopen", return_value=response) as urlopen:
        result = llm_client.ask_llm("Що таке REST API?")

    request = urlopen.call_args.args[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert result == "Відповідь українською"
    assert request.full_url == llm_client.GROQ_API_URL
    assert request.get_header("Authorization") == "Bearer test-key"
    assert payload["messages"] == [
        {"role": "system", "content": llm_client.SYSTEM_PROMPT},
        {"role": "user", "content": "Що таке REST API?"},
    ]
    assert urlopen.call_args.kwargs["timeout"] == llm_client.API_TIMEOUT_SECONDS


def test_ask_llm_does_not_call_api_without_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with patch.object(llm_client.urllib.request, "urlopen") as urlopen:
        result = llm_client.ask_llm("Запит")

    assert "додайте API-ключі" in result
    urlopen.assert_not_called()


@pytest.mark.parametrize(
    ("status_code", "message"),
    [
        (401, "Перевірте API-ключ"),
        (429, "ліміт запитів"),
        (500, "HTTP 500"),
    ],
)
def test_ask_llm_returns_readable_http_errors(monkeypatch, status_code, message):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    error = urllib.error.HTTPError(
        llm_client.GROQ_API_URL,
        status_code,
        "request failed",
        Message(),
        None,
    )

    with patch.object(
        llm_client.urllib.request,
        "urlopen",
        side_effect=error,
    ):
        result = llm_client.ask_llm("Запит")

    assert message in result


def test_ask_llm_includes_sanitized_http_error_detail(monkeypatch):
    api_key = "test-key"
    monkeypatch.setenv("LLM_API_KEY", api_key)
    error_body = json.dumps(
        {"error": {"message": f"Invalid request; Authorization: Bearer {api_key}"}}
    ).encode("utf-8")
    error = urllib.error.HTTPError(
        llm_client.GROQ_API_URL,
        400,
        "bad request",
        Message(),
        io.BytesIO(error_body),
    )

    with patch.object(
        llm_client.urllib.request,
        "urlopen",
        side_effect=error,
    ):
        result = llm_client.ask_llm("Запит")

    assert "HTTP 400" in result
    assert "Invalid request" in result
    assert api_key not in result


def test_ask_llm_reports_connection_errors(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    with patch.object(
        llm_client.urllib.request,
        "urlopen",
        side_effect=TimeoutError,
    ):
        result = llm_client.ask_llm("Запит")

    assert "Перевірте інтернет-з'єднання" in result


def test_ask_llm_rejects_multiline_key_without_echoing_it(monkeypatch):
    malformed_key = "test-key\nextra-line"
    monkeypatch.setenv("LLM_API_KEY", malformed_key)

    with patch.object(llm_client.urllib.request, "Request") as request:
        result = llm_client.ask_llm("Запит")

    assert result == llm_client.INVALID_KEY_FORMAT_MESSAGE
    assert malformed_key not in result
    request.assert_not_called()


def test_ask_llm_sanitizes_invalid_header_value(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    with (
        patch.object(
            llm_client.urllib.request,
            "Request",
            side_effect=ValueError("Invalid header value b'test-key'"),
        ),
        patch.object(llm_client.urllib.request, "urlopen") as urlopen,
    ):
        result = llm_client.ask_llm("Запит")

    assert result == llm_client.INVALID_REQUEST_MESSAGE
    assert "test-key" not in result
    urlopen.assert_not_called()


def test_ask_llm_tries_next_key_after_quota_error(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "first-key")
    llm_config.save_credentials({"groq": ["second-key"]})
    success = make_response(
        {"choices": [{"message": {"content": "Резервна відповідь"}}]}
    )
    quota_error = urllib.error.HTTPError(
        llm_client.GROQ_API_URL,
        429,
        "quota exceeded",
        Message(),
        None,
    )

    with patch.object(
        llm_client.urllib.request,
        "urlopen",
        side_effect=[quota_error, success],
    ) as urlopen:
        result = llm_client.ask_llm("Запит")

    assert result == "Резервна відповідь"
    assert [
        call.args[0].get_header("Authorization")
        for call in urlopen.call_args_list
    ] == ["Bearer first-key", "Bearer second-key"]


def test_all_quota_limited_keys_fall_through_to_next_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "groq-key-1")
    monkeypatch.setenv("GROQ_API_KEY_2", "groq-key-2")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    quota_errors = [
        urllib.error.HTTPError(
            llm_client.GROQ_API_URL,
            429,
            "quota exceeded",
            Message(),
            None,
        )
        for _ in range(2)
    ]
    gemini_response = make_response(
        {"candidates": [{"content": {"parts": [{"text": "Резерв Gemini"}]}}]}
    )

    with patch.object(
        llm_client.urllib.request,
        "urlopen",
        side_effect=[*quota_errors, gemini_response],
    ) as urlopen:
        result = llm_client.ask_llm("Запит")

    assert result == "Резерв Gemini"
    assert urlopen.call_count == 3
    assert "generateContent" in urlopen.call_args_list[2].args[0].full_url


def test_ask_llm_uses_next_provider_after_provider_error(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    groq_error = urllib.error.HTTPError(
        llm_client.GROQ_API_URL,
        503,
        "unavailable",
        Message(),
        None,
    )
    gemini_response = make_response(
        {
            "candidates": [
                {"content": {"parts": [{"text": "Відповідь Gemini"}]}}
            ]
        }
    )

    with patch.object(
        llm_client.urllib.request,
        "urlopen",
        side_effect=[groq_error, groq_error, gemini_response],
    ) as urlopen:
        result = llm_client.ask_llm("Запит")

    gemini_request = urlopen.call_args_list[2].args[0]
    assert result == "Відповідь Gemini"
    assert urlopen.call_args_list[0].args[0].full_url == llm_client.GROQ_API_URL
    assert urlopen.call_args_list[1].args[0].full_url == llm_client.GROQ_API_URL
    assert "gemini-2.5-flash:generateContent" in gemini_request.full_url
    assert gemini_request.get_header("X-goog-api-key") == "gemini-key"


def test_disabled_fallback_does_not_try_next_key(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "first-key")
    llm_config.save_credentials({"groq": ["second-key"]})
    llm_config.save_preferences(
        {
            "fallback_enabled": False,
            "provider_order": ["groq", "gemini"],
            "providers": default_providers(),
        }
    )
    quota_error = urllib.error.HTTPError(
        llm_client.GROQ_API_URL,
        429,
        "quota exceeded",
        Message(),
        None,
    )

    with patch.object(
        llm_client.urllib.request,
        "urlopen",
        side_effect=quota_error,
    ) as urlopen:
        result = llm_client.ask_llm("Запит")

    assert "ліміт запитів" in result
    urlopen.assert_called_once()


def test_credentials_file_contains_only_provider_keys(tmp_path, monkeypatch):
    credentials_path = tmp_path / ".llm_credentials.json"
    monkeypatch.setattr(llm_config, "CREDENTIALS_FILE", credentials_path)

    llm_config.save_credentials({"groq": ["secret"], "gemini": ["another-secret"]})

    assert json.loads(credentials_path.read_text(encoding="utf-8")) == {
        "groq": ["secret"],
        "gemini": ["another-secret"],
    }


def test_custom_openai_compatible_provider_supports_unlimited_keys():
    provider_id = "custom_openrouter"
    providers = default_providers()
    providers[provider_id] = {
        "name": "OpenRouter",
        "type": "openai_compatible",
        "api_url": "https://openrouter.ai/api/v1",
        "model": "openai/example-model",
    }
    llm_config.save_preferences(
        {
            "fallback_enabled": True,
            "provider_order": [provider_id, "groq", "gemini"],
            "providers": providers,
        }
    )
    keys = [f"key-{index}" for index in range(12)]
    llm_config.save_credentials({provider_id: keys})
    errors = [
        urllib.error.HTTPError(
            "https://openrouter.ai/api/v1/chat/completions",
            429,
            "quota exceeded",
            Message(),
            None,
        )
        for _key in keys[:-1]
    ]
    success = make_response(
        {"choices": [{"message": {"content": "Працює"}}]}
    )

    with patch.object(
        llm_client.urllib.request,
        "urlopen",
        side_effect=[*errors, success],
    ) as urlopen:
        result = llm_client.ask_llm("Запит")

    assert result == "Працює"
    assert len(urlopen.call_args_list) == len(keys)
    last_request = urlopen.call_args.args[0]
    assert last_request.full_url == "https://openrouter.ai/api/v1/chat/completions"
    assert last_request.get_header("Authorization") == "Bearer key-11"


def test_nvidia_endpoint_receives_documented_generation_parameters():
    provider_id = "custom_nvidia_gemma"
    providers = default_providers()
    providers[provider_id] = {
        "name": "NVIDIA Gemma",
        "type": "openai_compatible",
        "api_url": "https://integrate.api.nvidia.com/v1",
        "model": "google/gemma-4-31b-it",
    }
    llm_config.save_preferences(
        {
            "fallback_enabled": True,
            "provider_order": [provider_id, "groq", "gemini"],
            "providers": providers,
        }
    )
    llm_config.save_credentials({provider_id: ["nvidia-test-key"]})
    response = make_response(
        {"choices": [{"message": {"content": "Відповідь Gemma"}}]}
    )

    with patch.object(
        llm_client.urllib.request,
        "urlopen",
        return_value=response,
    ) as urlopen:
        result = llm_client.ask_llm("Запит")

    payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
    assert result == "Відповідь Gemma"
    assert payload["model"] == "google/gemma-4-31b-it"
    assert payload["max_tokens"] == 1024
    assert payload["temperature"] == 1.0
    assert payload["top_p"] == 0.95
    assert payload["stream"] is False


def test_quota_cooldown_expires_and_key_is_retried(monkeypatch):
    llm_config.save_credentials({"groq": ["one-key"]})
    current_time = [100.0]
    monkeypatch.setattr(llm_client.time, "monotonic", lambda: current_time[0])
    quota_error = urllib.error.HTTPError(
        "https://api.groq.com/openai/v1/chat/completions",
        429,
        "quota exceeded",
        Message(),
        None,
    )
    success = make_response(
        {"choices": [{"message": {"content": "Квота відновилась"}}]}
    )

    with patch.object(
        llm_client.urllib.request,
        "urlopen",
        side_effect=[quota_error, success],
    ) as urlopen:
        first_result = llm_client.ask_llm("Перший запит")
        second_result = llm_client.ask_llm("Запит під час паузи")
        current_time[0] += llm_client.QUOTA_COOLDOWN_SECONDS + 1
        third_result = llm_client.ask_llm("Повторний запит")

    assert "429" in first_result
    assert "пау" in second_result
    assert third_result == "Квота відновилась"
    assert urlopen.call_count == 2


def test_network_failure_retries_once_then_cools_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    gemini_response = make_response(
        {"candidates": [{"content": {"parts": [{"text": "Gemini відповів"}]}}]}
    )

    with patch.object(
        llm_client.urllib.request,
        "urlopen",
        side_effect=[
            urllib.error.URLError("offline"),
            urllib.error.URLError("offline"),
            gemini_response,
        ],
    ) as urlopen:
        result = llm_client.ask_llm("Запит")

    assert result == "Gemini відповів"
    assert urlopen.call_count == 3
    assert urlopen.call_args_list[0].args[0].full_url == (
        urlopen.call_args_list[1].args[0].full_url
    )
    assert "generateContent" in urlopen.call_args_list[2].args[0].full_url


def test_provider_is_retried_after_temporary_cooldown(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    current_time = [200.0]
    monkeypatch.setattr(llm_client.time, "monotonic", lambda: current_time[0])
    success = make_response(
        {"choices": [{"message": {"content": "Провайдер відновився"}}]}
    )

    with patch.object(
        llm_client.urllib.request,
        "urlopen",
        side_effect=[
            urllib.error.URLError("offline"),
            urllib.error.URLError("offline"),
            success,
        ],
    ) as urlopen:
        first_result = llm_client.ask_llm("Перший запит")
        paused_result = llm_client.ask_llm("Запит під час паузи")
        current_time[0] += llm_client.PROVIDER_COOLDOWN_SECONDS + 1
        recovered_result = llm_client.ask_llm("Повтор після паузи")

    assert "інтернет-з'єднання" in first_result
    assert "пау" in paused_result
    assert recovered_result == "Провайдер відновився"
    assert urlopen.call_count == 3


def test_custom_anthropic_provider_uses_messages_api():
    provider_id = "custom_anthropic"
    providers = default_providers()
    providers[provider_id] = {
        "name": "Anthropic",
        "type": "anthropic",
        "api_url": "https://api.anthropic.com",
        "model": "claude-model",
    }
    llm_config.save_preferences(
        {
            "fallback_enabled": True,
            "provider_order": [provider_id, "groq", "gemini"],
            "providers": providers,
        }
    )
    llm_config.save_credentials({provider_id: ["anthropic-key"]})
    response = make_response(
        {"content": [{"type": "text", "text": "Відповідь Anthropic"}]}
    )

    with patch.object(
        llm_client.urllib.request,
        "urlopen",
        return_value=response,
    ) as urlopen:
        result = llm_client.ask_llm("Запит")

    request = urlopen.call_args.args[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert result == "Відповідь Anthropic"
    assert request.full_url == "https://api.anthropic.com/v1/messages"
    assert request.get_header("X-api-key") == "anthropic-key"
    assert request.get_header("Anthropic-version") == "2023-06-01"
    assert payload["max_tokens"] == 1024


def test_authentication_failure_skips_key_until_configuration_changes():
    llm_config.save_credentials({"groq": ["invalid-key", "valid-key"]})
    auth_error = urllib.error.HTTPError(
        "https://api.groq.com/openai/v1/chat/completions",
        401,
        "unauthorized",
        Message(),
        None,
    )
    success = make_response(
        {"choices": [{"message": {"content": "Успішно"}}]}
    )
    with patch.object(
        llm_client.urllib.request,
        "urlopen",
        side_effect=[auth_error, success, success, success],
    ) as urlopen:
        first_result = llm_client.ask_llm("Перший запит")
        second_result = llm_client.ask_llm("Другий запит")
        llm_config.save_credentials(
            {"groq": ["invalid-key", "valid-key", "new-key"]}
        )
        third_result = llm_client.ask_llm("Після оновлення конфігурації")

    assert first_result == "Успішно"
    assert second_result == "Успішно"
    assert third_result == "Успішно"
    assert [call.args[0].get_header("Authorization") for call in urlopen.call_args_list] == [
        "Bearer invalid-key",
        "Bearer valid-key",
        "Bearer valid-key",
        "Bearer invalid-key",
    ]
