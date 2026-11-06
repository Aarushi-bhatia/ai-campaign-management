"""How every prompt is put together.

The order never changes: the fixed part first (same for every call for a brand),
then the campaign part, then an optional channel part, then the task. OpenAI caches long
matching starts, so the fixed part must stay byte-for-byte identical between calls.

Cache points are placed by hand. Left to itself, the API caches up to the end of the latest
message, so every call would also pay to store its one-off task (writes cost 1.25x input).
A prompt marks only the parts worth reusing: the fixed part always, the campaign part when
several calls share it, and the channel part (a channel's rules) when calls for assets on the
same channel share it. Tool loops are the exception: each round resends the last round's whole
prompt plus the tool results, so there the default (cache everything so far) is the right choice.
"""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class Image:
    """An image sent with a message, as a data URL. `label` is what the call log shows instead of the bytes."""

    data_url: str
    label: str


CachePoint = Literal["fixed", "campaign", "channel"]
BREAKPOINT = {"mode": "explicit"}


def _text(role: str, text: str, cache_point: bool) -> dict[str, Any]:
    """Always the same shape, marked or not, so a marked and an unmarked call share a cached start."""
    part: dict[str, Any] = {"type": "input_text", "text": text}
    if cache_point:
        part["prompt_cache_breakpoint"] = BREAKPOINT
    return {"role": role, "content": [part]}


@dataclass(frozen=True)
class Turn:
    role: Literal["user", "assistant"]
    content: str
    images: tuple[Image, ...] = ()

    def to_message(self, for_log: bool = False) -> dict[str, Any]:
        if not self.images:
            return {"role": self.role, "content": self.content}
        parts: list[dict[str, Any]] = [{"type": "input_text", "text": self.content}]
        parts += [
            {"type": "input_image", "image_url": f"<image: {image.label}>" if for_log else image.data_url,
             "detail": "low"}
            for image in self.images
        ]
        return {"role": self.role, "content": parts}


@dataclass(frozen=True)
class Prompt:
    fixed: str
    campaign: str = ""
    task: list[Turn] = field(default_factory=list)
    cache: tuple[CachePoint, ...] = ("fixed",)
    channel: str = ""
    """Text shared by calls for assets on one channel (its rules). It comes after the campaign part, so
    those calls share a cached start up to the end of it."""

    def to_input(self, for_log: bool = False, cache_points: bool = True) -> list[dict[str, Any]]:
        """With `cache_points` off, no part is marked and the API's default cache point applies."""
        def part(text: str, point: CachePoint) -> dict[str, Any]:
            return _text("developer", text, cache_points and point in self.cache)

        messages = [part(self.fixed, "fixed")]
        if self.campaign:
            messages.append(part(self.campaign, "campaign"))
        if self.channel:
            messages.append(part(self.channel, "channel"))
        messages.extend(turn.to_message(for_log) for turn in self.task)
        return messages


@dataclass(frozen=True)
class OutputSchema:
    """Asks the model to reply with JSON matching this schema."""

    name: str
    schema: dict[str, Any]


def strict_object(properties: dict[str, Any]) -> dict[str, Any]:
    """A JSON object schema in the strict form OpenAI requires: every field required, nothing extra."""
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


TEXT: dict[str, Any] = {"type": "string"}
TEXT_LIST: dict[str, Any] = {"type": "array", "items": TEXT}


def enum(*values: str) -> dict[str, Any]:
    return {"type": "string", "enum": list(values)}


def array_of(item: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": item}
