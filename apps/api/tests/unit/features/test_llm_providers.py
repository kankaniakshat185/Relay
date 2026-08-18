"""Exercises each provider's happy path and its exception-mapping —
`SynthesisError` normalization is the actual thing worth testing here,
since that's what lets `service.py` stay provider-agnostic."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import openai
import pytest
from anthropic import AuthenticationError as AnthropicAuthenticationError
from anthropic import PermissionDeniedError as AnthropicPermissionDeniedError
from google.genai import errors as genai_errors

from relay_api.features.context_search import llm_providers as lp

_SYSTEM = "system prompt"
_USER = "user prompt"


def _openai_style_response(answer: str, cited_indices: list[int]) -> SimpleNamespace:
    content = json.dumps({"answer": answer, "cited_indices": cited_indices})
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _openai_auth_error() -> openai.AuthenticationError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return openai.AuthenticationError(
        "invalid api key", response=httpx.Response(401, request=request), body=None
    )


def _openai_server_error() -> openai.APIError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return openai.APIError("upstream unavailable", request=request, body=None)


# --- OpenAI ---


async def test_openai_happy_path_parses_answer_and_indices() -> None:
    with patch.object(lp, "AsyncOpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create = AsyncMock(
            return_value=_openai_style_response("hello", [0, 2])
        )
        answer, indices = await lp.synthesize_openai(_SYSTEM, _USER, "sk-key", "gpt-4o-mini")

    assert answer == "hello"
    assert indices == [0, 2]
    mock_cls.assert_called_once_with(api_key="sk-key")


async def test_openai_authentication_error_maps_to_invalid_api_key() -> None:
    with patch.object(lp, "AsyncOpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create = AsyncMock(side_effect=_openai_auth_error())
        with pytest.raises(lp.SynthesisError) as exc_info:
            await lp.synthesize_openai(_SYSTEM, _USER, "sk-bad", "gpt-4o-mini")

    assert exc_info.value.reason == "invalid_api_key"


async def test_openai_other_api_error_maps_to_provider_error() -> None:
    with patch.object(lp, "AsyncOpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create = AsyncMock(
            side_effect=_openai_server_error()
        )
        with pytest.raises(lp.SynthesisError) as exc_info:
            await lp.synthesize_openai(_SYSTEM, _USER, "sk-key", "gpt-4o-mini")

    assert exc_info.value.reason == "provider_error"


# --- Groq (same SDK/exceptions as OpenAI, different base_url) ---


async def test_groq_happy_path_uses_json_object_format() -> None:
    with patch.object(lp, "AsyncOpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create = AsyncMock(
            return_value=_openai_style_response("hi from groq", [1])
        )
        answer, indices = await lp.synthesize_groq(_SYSTEM, _USER, "gsk-key", "llama-3.3-70b")

    assert answer == "hi from groq"
    assert indices == [1]
    mock_cls.assert_called_once_with(api_key="gsk-key", base_url=lp._GROQ_BASE_URL)


async def test_groq_authentication_error_maps_to_invalid_api_key() -> None:
    with patch.object(lp, "AsyncOpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create = AsyncMock(side_effect=_openai_auth_error())
        with pytest.raises(lp.SynthesisError) as exc_info:
            await lp.synthesize_groq(_SYSTEM, _USER, "gsk-bad", "llama-3.3-70b")

    assert exc_info.value.reason == "invalid_api_key"


# --- Anthropic ---


def _anthropic_tool_use_response(answer: str, cited_indices: list[int]) -> SimpleNamespace:
    block = SimpleNamespace(
        type="tool_use", input={"answer": answer, "cited_indices": cited_indices}
    )
    return SimpleNamespace(content=[block])


async def test_anthropic_happy_path_reads_tool_use_block() -> None:
    with patch.object(lp, "AsyncAnthropic") as mock_cls:
        mock_cls.return_value.messages.create = AsyncMock(
            return_value=_anthropic_tool_use_response("claude says hi", [0])
        )
        answer, indices = await lp.synthesize_anthropic(
            _SYSTEM, _USER, "sk-ant-key", "claude-haiku-4-5-20251001"
        )

    assert answer == "claude says hi"
    assert indices == [0]


async def test_anthropic_authentication_error_maps_to_invalid_api_key() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = AnthropicAuthenticationError(
        "invalid x-api-key", response=httpx.Response(401, request=request), body=None
    )
    with patch.object(lp, "AsyncAnthropic") as mock_cls:
        mock_cls.return_value.messages.create = AsyncMock(side_effect=error)
        with pytest.raises(lp.SynthesisError) as exc_info:
            await lp.synthesize_anthropic(_SYSTEM, _USER, "sk-ant-bad", "claude-haiku-4-5-20251001")

    assert exc_info.value.reason == "invalid_api_key"


async def test_anthropic_other_api_error_maps_to_provider_error() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = AnthropicPermissionDeniedError(
        "permission denied", response=httpx.Response(403, request=request), body=None
    )
    with patch.object(lp, "AsyncAnthropic") as mock_cls:
        mock_cls.return_value.messages.create = AsyncMock(side_effect=error)
        with pytest.raises(lp.SynthesisError) as exc_info:
            await lp.synthesize_anthropic(_SYSTEM, _USER, "sk-ant-key", "claude-haiku-4-5-20251001")

    assert exc_info.value.reason == "provider_error"


async def test_anthropic_response_with_no_tool_use_block_returns_empty() -> None:
    with patch.object(lp, "AsyncAnthropic") as mock_cls:
        mock_cls.return_value.messages.create = AsyncMock(
            return_value=SimpleNamespace(content=[SimpleNamespace(type="text", text="oops")])
        )
        answer, indices = await lp.synthesize_anthropic(
            _SYSTEM, _USER, "sk-ant-key", "claude-haiku-4-5-20251001"
        )

    assert answer == ""
    assert indices == []


# --- Gemini ---


async def test_gemini_happy_path_parses_json_text() -> None:
    fake_response = SimpleNamespace(
        text=json.dumps({"answer": "gemini says hi", "cited_indices": [2]})
    )
    with patch.object(lp.genai, "Client") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.aio.models.generate_content = AsyncMock(return_value=fake_response)

        answer, indices = await lp.synthesize_gemini(
            _SYSTEM, _USER, "gemini-key", "gemini-2.5-flash"
        )

    assert answer == "gemini says hi"
    assert indices == [2]


async def test_gemini_401_client_error_maps_to_invalid_api_key() -> None:
    error = genai_errors.ClientError(401, {"error": {"message": "API key not valid"}})
    with patch.object(lp.genai, "Client") as mock_cls:
        mock_cls.return_value.aio.models.generate_content = AsyncMock(side_effect=error)
        with pytest.raises(lp.SynthesisError) as exc_info:
            await lp.synthesize_gemini(_SYSTEM, _USER, "gemini-bad", "gemini-2.5-flash")

    assert exc_info.value.reason == "invalid_api_key"


async def test_gemini_400_client_error_maps_to_provider_error() -> None:
    error = genai_errors.ClientError(400, {"error": {"message": "bad request"}})
    with patch.object(lp.genai, "Client") as mock_cls:
        mock_cls.return_value.aio.models.generate_content = AsyncMock(side_effect=error)
        with pytest.raises(lp.SynthesisError) as exc_info:
            await lp.synthesize_gemini(_SYSTEM, _USER, "gemini-key", "gemini-2.5-flash")

    assert exc_info.value.reason == "provider_error"


async def test_gemini_server_error_maps_to_provider_error() -> None:
    error = genai_errors.ServerError(500, {"error": {"message": "internal error"}})
    with patch.object(lp.genai, "Client") as mock_cls:
        mock_cls.return_value.aio.models.generate_content = AsyncMock(side_effect=error)
        with pytest.raises(lp.SynthesisError) as exc_info:
            await lp.synthesize_gemini(_SYSTEM, _USER, "gemini-key", "gemini-2.5-flash")

    assert exc_info.value.reason == "provider_error"


# --- Registry ---


def test_registry_has_all_four_providers() -> None:
    assert set(lp.SYNTHESIS_PROVIDERS.keys()) == {"openai", "groq", "anthropic", "gemini"}
