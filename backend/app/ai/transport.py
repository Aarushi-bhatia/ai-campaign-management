"""The thin layer that actually talks to OpenAI. Tests swap it for a fake."""

import json
from dataclasses import dataclass
from typing import Any, Protocol

from openai import OpenAI

from app.ai.prompt import OutputSchema, Prompt


@dataclass(frozen=True)
class AiRequest:
    model: str
    prompt: Prompt
    output_schema: OutputSchema | None = None
    cache_key: str | None = None
    tools: tuple[dict[str, Any], ...] = ()
    """Function tool definitions the model may call."""
    tool_turns: tuple[dict[str, Any], ...] = ()
    """Earlier tool calls and their results in this exchange, sent after the prompt."""
    allow_tools: bool = True
    cache_points: bool = True
    """Hand-placed cache points (see `app.ai.prompt`). Off for tool loops, which use the API's default."""

    def to_payload(self, for_log: bool = False) -> dict[str, Any]:
        """The exact arguments sent to the Responses API. Also what "View prompt" shows.

        For the log, images are replaced by a short label so the log stays readable.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "input": [*self.prompt.to_input(for_log, self.cache_points), *self.tool_turns],
        }
        if self.cache_points:
            payload["prompt_cache_options"] = {"mode": "explicit"}
        if self.tools:
            payload["tools"] = list(self.tools)
            payload["tool_choice"] = "auto" if self.allow_tools else "none"
        if self.cache_key:
            payload["prompt_cache_key"] = self.cache_key
        if self.output_schema:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": self.output_schema.name,
                    "schema": self.output_schema.schema,
                    "strict": True,
                }
            }
        return payload


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class AiResult:
    text: str
    model: str
    """The model that actually answered, as reported by the API (may be a dated snapshot)."""
    tokens_in: int
    tokens_cached: int
    tokens_cache_write: int
    tokens_out: int
    tool_calls: tuple[ToolCall, ...] = ()
    output_items: tuple[dict[str, Any], ...] = ()
    """Everything the model returned, in the form to send back when the exchange continues."""


def json_part(text: str) -> str:
    """The JSON object in a reply. Now and then the model writes a sentence before it, even when asked for
    JSON only; the sentence is dropped. A reply with no JSON object is returned as it is."""
    stripped = text.strip()
    if stripped.startswith("{"):
        return stripped
    decoder = json.JSONDecoder()
    for start in (i for i, ch in enumerate(text) if ch == "{"):
        try:
            _, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        return text[start:end]
    return text


EMBEDDING_SIZE = 1536
"""Fixed so the stored vectors keep their shape if the embedding model is swapped."""


@dataclass(frozen=True)
class EmbedRequest:
    model: str
    texts: list[str]

    def to_payload(self) -> dict[str, Any]:
        return {"model": self.model, "input": self.texts, "dimensions": EMBEDDING_SIZE}


@dataclass(frozen=True)
class EmbedResult:
    vectors: list[list[float]]
    model: str
    tokens_in: int


class AiTransport(Protocol):
    def send(self, request: AiRequest) -> AiResult: ...

    def embed(self, request: EmbedRequest) -> EmbedResult: ...


REQUEST_TIMEOUT_SECONDS = 300
"""A reply that takes longer than this has hung; it fails and is logged instead of blocking the chat."""


class OpenAiTransport:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: OpenAI | None = None

    def send(self, request: AiRequest) -> AiResult:
        response = self._openai().responses.create(**request.to_payload())
        usage = response.usage
        details = usage.input_tokens_details if usage else None
        items = tuple(item.model_dump(mode="json", exclude_none=True, by_alias=True) for item in response.output)
        return AiResult(
            tool_calls=tuple(
                ToolCall(item["call_id"], item["name"], item["arguments"]) for item in items if item["type"] == "function_call"
            ),
            output_items=items,
            text=json_part(response.output_text) if request.output_schema else response.output_text,
            model=response.model,
            tokens_in=usage.input_tokens if usage else 0,
            tokens_cached=(details.cached_tokens if details else 0) or 0,
            tokens_cache_write=(details.cache_write_tokens if details else 0) or 0,
            tokens_out=usage.output_tokens if usage else 0,
        )

    def embed(self, request: EmbedRequest) -> EmbedResult:
        response = self._openai().embeddings.create(**request.to_payload())
        return EmbedResult(
            vectors=[item.embedding for item in response.data],
            model=response.model,
            tokens_in=response.usage.prompt_tokens,
        )

    def _openai(self) -> OpenAI:
        """Created on first use, so the app still starts and shows data when no key is set."""
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY is not set. Add it to the .env file and restart.")
        if self._client is None:
            self._client = OpenAI(api_key=self._api_key, timeout=REQUEST_TIMEOUT_SECONDS)
        return self._client
