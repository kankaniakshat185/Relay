"""BYOK synthesis providers (ADR 0008) — OpenAI, Groq, Anthropic, Gemini.

Every provider implements the same shape: given a system prompt, a user
prompt, an API key, and a model name, return `(answer, cited_indices)`, or
raise `SynthesisError` with a normalized reason. Each SDK has a different
structured-output mechanism (OpenAI/Groq: JSON response format; Anthropic:
forced tool use; Gemini: `response_schema`) *and* a different exception
hierarchy — both are handled here, once, so `service.py` never needs to
know which provider it's talking to.

Groq specifically reuses the `openai` SDK pointed at Groq's OpenAI-
compatible endpoint rather than a separate client library — there's no
Groq-specific SDK feature this needs.

This is a single user-initiated call, not a batch job — there's no retry/
backoff here on purpose. A transient failure just surfaces as
"provider_error" and the user retries by searching again; there's no
volume of calls where backoff would actually help.
"""

import json
from collections.abc import Awaitable, Callable
from typing import Literal

import anthropic
import openai
from anthropic import AsyncAnthropic
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONSchema

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"

SynthesisErrorReason = Literal["invalid_api_key", "provider_error"]


class SynthesisError(Exception):
    """Normalizes every provider's own exception hierarchy into one shape
    `service.py` can handle without importing four different SDKs' error
    types itself."""

    def __init__(self, reason: SynthesisErrorReason, message: str) -> None:
        self.reason: SynthesisErrorReason = reason
        super().__init__(message)


_JSON_SCHEMA: ResponseFormatJSONSchema = {
    "type": "json_schema",
    "json_schema": {
        "name": "context_search_answer",
        "schema": {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "cited_indices": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["answer", "cited_indices"],
            "additionalProperties": False,
        },
    },
}


def _parse_json_answer(content: str | None) -> tuple[str, list[int]]:
    parsed = json.loads(content or "{}")
    return parsed.get("answer", ""), parsed.get("cited_indices", [])


async def synthesize_openai(
    system_prompt: str, user_prompt: str, api_key: str, model: str
) -> tuple[str, list[int]]:
    client = AsyncOpenAI(api_key=api_key)
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        response = await client.chat.completions.create(
            model=model, messages=messages, response_format=_JSON_SCHEMA
        )
    except openai.AuthenticationError as exc:
        raise SynthesisError("invalid_api_key", str(exc)) from exc
    except openai.APIError as exc:
        raise SynthesisError("provider_error", str(exc)) from exc

    return _parse_json_answer(response.choices[0].message.content)


async def synthesize_groq(
    system_prompt: str, user_prompt: str, api_key: str, model: str
) -> tuple[str, list[int]]:
    client = AsyncOpenAI(api_key=api_key, base_url=_GROQ_BASE_URL)
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"{user_prompt}\n\nRespond with JSON only: "
            '{"answer": string, "cited_indices": number[]}.',
        },
    ]
    # Groq's OpenAI-compatible endpoint doesn't reliably support the
    # stricter `json_schema` format across all hosted models — `json_object`
    # plus an explicit shape instruction in the prompt is the portable path.
    try:
        response = await client.chat.completions.create(
            model=model, messages=messages, response_format={"type": "json_object"}
        )
    except openai.AuthenticationError as exc:
        raise SynthesisError("invalid_api_key", str(exc)) from exc
    except openai.APIError as exc:
        raise SynthesisError("provider_error", str(exc)) from exc

    return _parse_json_answer(response.choices[0].message.content)


async def synthesize_anthropic(
    system_prompt: str, user_prompt: str, api_key: str, model: str
) -> tuple[str, list[int]]:
    client = AsyncAnthropic(api_key=api_key)
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[
                {
                    "name": "answer_with_citations",
                    "description": "Report the answer and which candidate indices it draws from.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "answer": {"type": "string"},
                            "cited_indices": {"type": "array", "items": {"type": "integer"}},
                        },
                        "required": ["answer", "cited_indices"],
                    },
                }
            ],
            tool_choice={"type": "tool", "name": "answer_with_citations"},
        )
    except anthropic.AuthenticationError as exc:
        raise SynthesisError("invalid_api_key", str(exc)) from exc
    except anthropic.APIError as exc:
        raise SynthesisError("provider_error", str(exc)) from exc

    for block in response.content:
        if block.type == "tool_use" and isinstance(block.input, dict):
            answer = block.input.get("answer", "")
            cited_indices = block.input.get("cited_indices", [])
            indices = cited_indices if isinstance(cited_indices, list) else []
            return str(answer), [int(i) for i in indices]
    return "", []


async def synthesize_gemini(
    system_prompt: str, user_prompt: str, api_key: str, model: str
) -> tuple[str, list[int]]:
    client = genai.Client(api_key=api_key)
    try:
        response = await client.aio.models.generate_content(
            model=model,
            contents=user_prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema={
                    "type": "OBJECT",
                    "properties": {
                        "answer": {"type": "STRING"},
                        "cited_indices": {"type": "ARRAY", "items": {"type": "INTEGER"}},
                    },
                    "required": ["answer", "cited_indices"],
                },
            ),
        )
    except genai_errors.ClientError as exc:
        # ClientError covers all 4xx — 401/403 specifically mean the key
        # itself is the problem, anything else (400 bad request, etc.) is
        # a provider-side/request issue, not something a new key fixes.
        reason: SynthesisErrorReason = (
            "invalid_api_key" if exc.code in (401, 403) else "provider_error"
        )
        raise SynthesisError(reason, str(exc)) from exc
    except genai_errors.APIError as exc:
        raise SynthesisError("provider_error", str(exc)) from exc

    return _parse_json_answer(response.text)


SynthesizeFn = Callable[[str, str, str, str], Awaitable[tuple[str, list[int]]]]

SYNTHESIS_PROVIDERS: dict[str, SynthesizeFn] = {
    "openai": synthesize_openai,
    "groq": synthesize_groq,
    "anthropic": synthesize_anthropic,
    "gemini": synthesize_gemini,
}
