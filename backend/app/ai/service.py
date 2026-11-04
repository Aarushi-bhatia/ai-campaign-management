"""The single path to the AI. Every call is logged to the database and to a log file.

The log is written in its own short transaction, never the caller's: logging a call must not save the caller's
unfinished work or release the row locks it holds, and a call that failed is still logged when the caller then
rolls back."""

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.ai.models import AiCall
from app.ai.pricing import cost_usd
from app.ai.prompt import OutputSchema, Prompt
from app.ai.transport import AiRequest, AiResult, AiTransport, EmbedRequest, ToolCall
from app.config import ModelSize, Settings

_log_file_lock = threading.Lock()


@dataclass(frozen=True)
class AiReply:
    text: str
    call_id: int
    """The last call. A reply that used tools took several calls; all of them are in `call_ids`."""
    call_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class Tool:
    """A function the model may call. `run` gets the parsed arguments and returns text for the model."""

    name: str
    description: str
    parameters: dict[str, Any]
    run: Callable[[dict[str, Any]], str]

    def definition(self) -> dict[str, Any]:
        return {"type": "function", "name": self.name, "description": self.description,
                "parameters": self.parameters, "strict": True}


class AiCallFailed(Exception):
    """The AI request failed. The failed call is still logged, with its error."""

    def __init__(self, call_id: int, reason: str) -> None:
        super().__init__(reason)
        self.call_id = call_id


class AiService:
    def __init__(self, session: Session, transport: AiTransport, settings: Settings,
                 log_sessions: Callable[[], Session] | None = None) -> None:
        """`log_sessions` opens the sessions calls are logged in; by default, new ones on the caller's database.
        A call's chat and brand must already be saved, since the log can't see the caller's unsaved rows."""
        self._transport = transport
        self._settings = settings
        self._log_sessions = log_sessions or sessionmaker(session.get_bind(), expire_on_commit=False)

    def complete(
        self,
        *,
        step: str,
        size: ModelSize,
        prompt: Prompt,
        chat_id: int | None = None,
        brand_id: int | None = None,
        output_schema: OutputSchema | None = None,
        cache_key: str | None = None,
    ) -> AiReply:
        request = AiRequest(
            model=self._settings.model_for(size),
            prompt=prompt,
            output_schema=output_schema,
            cache_key=cache_key,
        )
        result, call_id = self._send(step, size, request, chat_id, brand_id)
        return AiReply(text=result.text, call_id=call_id, call_ids=(call_id,))

    def _send(
        self, step: str, size: ModelSize, request: AiRequest, chat_id: int | None, brand_id: int | None
    ) -> tuple[AiResult, int]:
        call = AiCall(
            step=fit_step(step),
            size=size.value,
            model=request.model,
            chat_id=chat_id,
            brand_id=brand_id,
            request=request.to_payload(for_log=True),
        )
        started = time.monotonic()
        try:
            result = self._transport.send(request)
        except Exception as error:
            raise AiCallFailed(self._finish(call, started, error=repr(error)).id, str(error)) from error
        call.model = result.model
        call.tokens_in = result.tokens_in
        call.tokens_cached = result.tokens_cached
        call.tokens_cache_write = result.tokens_cache_write
        call.tokens_out = result.tokens_out
        call.cost_usd = cost_usd(
            result.model, result.tokens_in, result.tokens_cached, result.tokens_cache_write, result.tokens_out
        )
        call.response_text = result.text or _describe_tool_calls(result)
        return result, self._finish(call, started).id

    def complete_with_tools(
        self,
        *,
        step: str,
        size: ModelSize,
        prompt: Prompt,
        tools: list[Tool],
        chat_id: int | None = None,
        brand_id: int | None = None,
        output_schema: OutputSchema | None = None,
        cache_key: str | None = None,
        max_rounds: int = 6,
    ) -> AiReply:
        """Lets the model call tools until it answers. Every round is its own logged call.

        On the last round tools are switched off, so the model has to answer with what it has.
        """
        by_name = {tool.name: tool for tool in tools}
        turns: list[dict[str, Any]] = []
        call_ids: list[int] = []
        for round_number in range(1, max_rounds + 1):
            request = AiRequest(
                model=self._settings.model_for(size), prompt=prompt, output_schema=output_schema, cache_key=cache_key,
                tools=tuple(tool.definition() for tool in tools), tool_turns=tuple(turns),
                allow_tools=round_number < max_rounds, cache_points=False,
            )
            result, call_id = self._send(f"{step} (round {round_number})", size, request, chat_id, brand_id)
            call_ids.append(call_id)
            if not result.tool_calls:
                return AiReply(text=result.text, call_id=call_id, call_ids=tuple(call_ids))
            turns.extend(result.output_items)
            for call in result.tool_calls:
                turns.append({"type": "function_call_output", "call_id": call.call_id, "output": _run(by_name, call)})
        raise AiCallFailed(call_ids[-1], "The model kept calling tools without answering.")

    def embed(
        self, *, step: str, texts: list[str], brand_id: int | None = None, chat_id: int | None = None
    ) -> list[list[float]]:
        """Turns texts into search vectors, in one request."""
        request = EmbedRequest(model=self._settings.model_embedding, texts=texts)
        call = AiCall(step=fit_step(step), size="embedding", model=request.model, brand_id=brand_id, chat_id=chat_id,
                      request=request.to_payload())
        started = time.monotonic()
        try:
            result = self._transport.embed(request)
        except Exception as error:
            raise AiCallFailed(self._finish(call, started, error=repr(error)).id, str(error)) from error
        call.model = result.model
        call.tokens_in = result.tokens_in
        call.cost_usd = cost_usd(result.model, result.tokens_in, 0, 0, 0)
        call.response_text = f"{len(result.vectors)} vectors"
        self._finish(call, started)
        return result.vectors

    def _finish(self, call: AiCall, started: float, error: str | None = None) -> AiCall:
        call.duration_ms = int((time.monotonic() - started) * 1000)
        call.error = error
        with self._log_sessions() as log:
            log.add(call)
            log.commit()
        self._append_to_log_file(call)
        return call

    def _append_to_log_file(self, call: AiCall) -> None:
        entry: dict[str, Any] = {
            "id": call.id,
            "at": call.created_at.isoformat(),
            "step": call.step,
            "model": call.model,
            "chat_id": call.chat_id,
            "brand_id": call.brand_id,
            "tokens_in": call.tokens_in,
            "tokens_cached": call.tokens_cached,
            "tokens_cache_write": call.tokens_cache_write,
            "tokens_out": call.tokens_out,
            "cost_usd": call.cost_usd,
            "duration_ms": call.duration_ms,
            "request": call.request,
            "response": call.response_text,
            "error": call.error,
        }
        path = self._settings.ai_log_file
        path.parent.mkdir(parents=True, exist_ok=True)
        with _log_file_lock, path.open("a", encoding="utf-8") as log:
            log.write(json.dumps(entry, ensure_ascii=False) + "\n")


STEP_LENGTH = AiCall.__table__.c.step.type.length


def fit_step(step: str) -> str:
    """A step label short enough for the log. Labels can hold a file path, and a long path must not
    stop the call from being logged (which would fail the whole job). The start and end are kept."""
    if len(step) <= STEP_LENGTH:
        return step
    keep = STEP_LENGTH - 1
    return f"{step[: keep // 2]}…{step[-(keep - keep // 2):]}"


def _run(by_name: dict[str, Tool], call: ToolCall) -> str:
    """Runs one tool call. Mistakes go back to the model as text, so it can correct itself."""
    tool = by_name.get(call.name)
    if tool is None:
        return f"There is no tool called {call.name}."
    try:
        return tool.run(json.loads(call.arguments))
    except (ValueError, KeyError, TypeError) as error:
        return f"That call failed: {error}"


def _describe_tool_calls(result: AiResult) -> str:
    return "Called tools: " + "; ".join(f"{c.name}({c.arguments})" for c in result.tool_calls)
