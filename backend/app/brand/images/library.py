"""The brand's image library as the rest of the app sees it, and picking images for an asset."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.service import AiService
from app.brand.images import channel_rules
from app.brand.images.picking import (
    RANK_SCHEMA, AssetSpec, ImageView, PickResult, checked_choice, rank_prompt, split,
)
from app.brand.models import Brand, BrandDecision, BrandFile, ImageInfo
from app.config import ModelSize

TITLE_KEYS = ("title", "name", "caption")
DESCRIPTION_KEYS = ("description", "desc", "alt", "alt_text", "caption", "summary")
TYPE_KEYS = ("type", "category", "kind", "image_type")
TAG_KEYS = ("tags", "keywords", "labels")


def field_from(record: dict, keys: tuple[str, ...]) -> str:
    """The first non-empty text field among `keys` in an image info record."""
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def tags_from(record: dict) -> list[str]:
    for key in TAG_KEYS:
        value = record.get(key)
        if isinstance(value, list):
            return [str(tag) for tag in value]
        if isinstance(value, str) and value.strip():
            return [tag.strip() for tag in value.split(",") if tag.strip()]
    return []


def image_views(session: Session, brand_id: int) -> list[ImageView]:
    overrides = {
        d.target: d.value
        for d in session.scalars(
            select(BrandDecision).where(BrandDecision.brand_id == brand_id, BrandDecision.kind == "image_usable")
        )
    }
    rows = session.execute(
        select(ImageInfo, BrandFile.path)
        .join(BrandFile, BrandFile.id == ImageInfo.file_id)
        .where(ImageInfo.brand_id == brand_id)
        .order_by(BrandFile.path)
    )
    return [
        ImageView(
            id=info.id, path=path, title=info.title, description=info.description, image_type=info.image_type,
            tags=tuple(info.tags), width=info.width, height=info.height, transparent=info.transparent,
            notes=info.notes, usable_override=overrides.get(path),
        )
        for info, path in rows
    ]


def rules_for(brand: Brand) -> dict:
    return brand.image_rules or channel_rules.empty_rules()


def pick(
    session: Session, ai: AiService, brand: Brand, spec: AssetSpec, chat_id: int | None = None, step: str | None = None
) -> PickResult:
    """Blocks what can't be used, then asks the model to rank the rest. No AI call when nothing is left."""
    rules = rules_for(brand)
    candidates, blocked = split(image_views(session, brand.id), spec, rules["channels"])
    if not candidates:
        return PickResult(suggestion="No image in the library is cleared for this asset.", blocked=blocked)
    reply = ai.complete(
        step=step or f"Image choice ({spec.asset_type}, {spec.channel})",
        size=ModelSize.MEDIUM,
        prompt=rank_prompt(spec, candidates, rules),
        output_schema=RANK_SCHEMA,
        brand_id=brand.id,
        chat_id=chat_id,
    )
    choices, suggestion = checked_choice(reply.text, candidates)
    return PickResult(choices=choices, suggestion=suggestion, blocked=blocked, call_id=reply.call_id)
