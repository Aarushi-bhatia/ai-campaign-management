"""A stand-in for OpenAI that returns scripted replies, for tests."""

import hashlib
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass

from app.ai.transport import EMBEDDING_SIZE, AiRequest, AiResult, EmbedRequest, EmbedResult, ToolCall


@dataclass(frozen=True)
class CallTools:
    """A scripted reply that calls tools instead of answering: a list of (tool name, arguments)."""

    calls: list[tuple[str, dict]]


Reply = str | CallTools | Callable[[AiRequest], "str | CallTools"]


class FakeTransport:
    def __init__(self, replies: list[Reply] | None = None, default: Reply = "OK") -> None:
        self._replies = list(replies or [])
        self._default = default
        self._lock = threading.Lock()
        self.requests: list[AiRequest] = []
        self.embed_requests: list[EmbedRequest] = []
        self.answering_model: str | None = None
        """Set to pretend the API answered with a different model name, such as a dated snapshot."""

    def queue(self, *replies: Reply) -> None:
        self._replies.extend(replies)

    def send(self, request: AiRequest) -> AiResult:
        with self._lock:
            self.requests.append(request)
            reply = self._replies.pop(0) if self._replies else self._default
        answer = reply(request) if callable(reply) else reply
        tokens_in = sum(len(str(m)) for m in request.to_payload(for_log=True)["input"]) // 4
        if isinstance(answer, CallTools):
            calls = tuple(
                ToolCall(f"call_{len(self.requests)}_{i}", name, json.dumps(args)) for i, (name, args) in enumerate(answer.calls)
            )
            items = tuple(
                {"type": "function_call", "call_id": c.call_id, "name": c.name, "arguments": c.arguments} for c in calls
            )
            return AiResult("", self.answering_model or request.model, tokens_in, 0, 0, 10, calls, items)
        text = answer
        return AiResult(
            text=text,
            model=self.answering_model or request.model,
            tokens_in=tokens_in,
            tokens_cached=0,
            tokens_cache_write=0,
            tokens_out=len(text) // 4,
        )

    def embed(self, request: EmbedRequest) -> EmbedResult:
        with self._lock:
            self.embed_requests.append(request)
        return EmbedResult(
            vectors=[_vector_for(text) for text in request.texts],
            model=request.model,
            tokens_in=sum(len(text) for text in request.texts) // 4,
        )


def _vector_for(text: str) -> list[float]:
    """The same text always gets the same vector."""
    seed = hashlib.sha256(text.encode()).digest()
    return [seed[i % len(seed)] / 255 for i in range(EMBEDDING_SIZE)]
