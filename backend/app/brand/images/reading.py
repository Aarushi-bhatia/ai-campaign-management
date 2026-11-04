"""The image steps of reading a brand. Each keeps work whose input hasn't changed."""

import hashlib
import json
import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.service import AiCallFailed, AiService
from app.ai.transport import AiTransport
from app.brand.files import storage_path
from app.brand.images import channel_rules, info, notes
from app.brand.images.library import DESCRIPTION_KEYS, TITLE_KEYS, TYPE_KEYS, field_from, tags_from
from app.brand.models import Brand, BrandFile, ImageInfo
from app.brand.settle import usable_facts
from app.config import ModelSize, Settings

log = logging.getLogger(__name__)

WORKERS = 8
_TYPE_WORDS = (
    ("screenshot", "product_screenshot"), ("photo", "photography"), ("illustration", "illustration"),
    ("logo", "logo"), ("icon", "icon"), ("chart", "chart"), ("template", "social_template"),
    ("abstract", "abstract_graphic"), ("background", "abstract_graphic"),
)


@dataclass(frozen=True)
class ImageSteps:
    sessions: sessionmaker[Session]
    transport: AiTransport
    settings: Settings
    phase: Callable[[int, str, int], None]
    bump: Callable[[int], None]

    def record_info(self, brand_id: int) -> None:
        """Matches the image info file to the images and measures every image. No AI."""
        with self.sessions() as session:
            files = list(session.scalars(select(BrandFile).where(BrandFile.brand_id == brand_id)))
            images = [f for f in files if f.kind == "image"]
            data_files = [(f.path, self._path(brand_id, f).read_bytes()) for f in files if f.kind == "data"]
            records = info.records_by_image(data_files, [f.path for f in images])
            existing = {i.file_id: i for i in session.scalars(select(ImageInfo).where(ImageInfo.brand_id == brand_id))}
            for image in images:
                record = records.get(image.path, {})
                source = _hash(notes.DESCRIBE_VERSION, image.sha256, record)
                row = existing.get(image.id)
                if row and row.source_hash == source:
                    continue
                width, height, transparent = info.measure(self._path(brand_id, image))
                row = row or ImageInfo(brand_id=brand_id, file_id=image.id)
                description = field_from(record, DESCRIPTION_KEYS)
                thin = len(description.split()) < notes.SHORT_DESCRIPTION_WORDS
                row.record, row.title, row.tags = record, field_from(record, TITLE_KEYS), tags_from(record)
                row.description, row.description_source = description, "" if thin else "file"
                row.image_type = _image_type(field_from(record, TYPE_KEYS))
                row.width, row.height, row.transparent = width, height, transparent
                row.source_hash, row.describe_call_id = source, None
                session.add(row)
            session.commit()

    def describe(self, brand_id: int) -> None:
        """Vision descriptions for images with no description. SVGs get one from their name."""
        with self.sessions() as session:
            pending = [
                (row.id, path)
                for row, path in session.execute(
                    select(ImageInfo, BrandFile.path).join(BrandFile, BrandFile.id == ImageInfo.file_id)
                    .where(ImageInfo.brand_id == brand_id, ImageInfo.description_source == "")
                )
            ]
        self.phase(brand_id, "images", len(pending))
        with ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="image") as pool:
            list(pool.map(lambda item: self._describe_one(brand_id, *item), pending))

    def read_notes(self, brand_id: int) -> None:
        """Turns each image's rights and restrictions into fields, in batches, judged against the brand's rules."""
        with self.sessions() as session:
            brand_rules = _brand_image_rules(session, brand_id)
            rows = session.execute(
                select(ImageInfo, BrandFile.path).join(BrandFile, BrandFile.id == ImageInfo.file_id)
                .where(ImageInfo.brand_id == brand_id).order_by(ImageInfo.id)
            ).all()
            rules_hash = _hash(brand_rules)
            pending = [
                (row.id, path, _notes_input(row, path))
                for row, path in rows
                if row.notes_hash != _hash(notes.NOTES_VERSION, rules_hash, _notes_input(row, path))
            ]
        batches = [pending[i : i + notes.NOTES_BATCH] for i in range(0, len(pending), notes.NOTES_BATCH)]
        self.phase(brand_id, "image_notes", len(batches))
        with ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="image") as pool:
            list(pool.map(lambda batch: self._notes_batch(brand_id, batch, brand_rules, rules_hash), batches))

    def channel_rules(self, brand_id: int) -> None:
        """Per-channel image rules from the brand's winning facts about images."""
        with self.sessions() as session:
            brand = session.get_one(Brand, brand_id)
            lines = _brand_image_rules(session, brand_id)
            source = channel_rules.source_hash(lines)
            if brand.image_rules_hash == source:
                return
            if not lines:
                brand.image_rules, brand.image_rules_hash = channel_rules.empty_rules(), source
                session.commit()
                return
            self.phase(brand_id, "image_rules", 1)
            reply = AiService(session, self.transport, self.settings, self.sessions).complete(
                step="Brand reading: image rules per channel",
                size=ModelSize.MEDIUM,
                prompt=channel_rules.prompt_for(lines),
                output_schema=channel_rules.SCHEMA,
                brand_id=brand_id,
            )
            brand.image_rules = channel_rules.checked_rules(reply.text)
            brand.image_rules_hash, brand.image_rules_call_id = source, reply.call_id
            session.commit()

    def _describe_one(self, brand_id: int, info_id: int, path: str) -> None:
        with self.sessions() as session:
            row = session.get_one(ImageInfo, info_id)
            data_url = info.vision_data_url(storage_path(self.settings.data_dir, brand_id, path))
            if data_url is None:
                row.description = row.title or _from_name(path)
                row.description_source = "name"
                row.image_type = row.image_type or _image_type(path)
            else:
                try:
                    reply = AiService(session, self.transport, self.settings, self.sessions).complete(
                        step=f"Brand reading: image description ({path})",
                        size=ModelSize.SMALL,
                        prompt=notes.describe_prompt(path, row.title, row.description, data_url),
                        output_schema=notes.DESCRIBE_SCHEMA,
                        brand_id=brand_id,
                    )
                    described = json.loads(reply.text)
                    row.description, row.description_source = described["description"].strip(), "ai"
                    row.image_type = row.image_type or described["image_type"]
                    row.describe_call_id = reply.call_id
                except (AiCallFailed, ValueError, KeyError):
                    log.exception("Describing %s failed; it will be tried again on the next read", path)
            session.commit()
        self.bump(brand_id)

    def _notes_batch(self, brand_id: int, batch: list[tuple[int, str, dict]], brand_rules: list[str], rules_hash: str) -> None:
        with self.sessions() as session:
            try:
                reply = AiService(session, self.transport, self.settings, self.sessions).complete(
                    step=f"Brand reading: image rights and restrictions ({batch[0][1]} and {len(batch) - 1} more)",
                    size=ModelSize.SMALL,
                    prompt=notes.notes_prompt(
                        date.today().isoformat(), brand_rules, [{"id": i, **data} for i, _, data in batch]
                    ),
                    output_schema=notes.NOTES_SCHEMA,
                    brand_id=brand_id,
                )
                found = notes.checked_notes(reply.text, {i for i, _, _ in batch})
            except (AiCallFailed, ValueError, KeyError):
                log.exception("Reading image notes failed; they will be tried again on the next read")
                found = {}
            # Every image in the batch is here because its notes are out of date (its record or the brand's
            # image rules changed). Notes that couldn't be read again are cleared rather than kept: an old
            # "usable" must not stand for an image that is now restricted. Until the next read it is blocked.
            for info_id, _, data in batch:
                row = session.get_one(ImageInfo, info_id)
                if info_id in found:
                    row.notes, row.notes_call_id = found[info_id], reply.call_id
                    row.notes_hash = _hash(notes.NOTES_VERSION, rules_hash, data)
                else:
                    row.notes, row.notes_call_id = None, None
            session.commit()
        self.bump(brand_id)

    def _path(self, brand_id: int, file: BrandFile) -> Path:
        return storage_path(self.settings.data_dir, brand_id, file.path)


def _brand_image_rules(session: Session, brand_id: int) -> list[str]:
    """The brand's winning facts about images, one per line."""
    return channel_rules.image_fact_lines(
        [(f.subject, f.attribute, f.value, f.scope, d.path) for f, d in usable_facts(session, brand_id)]
    )


def _notes_input(row: ImageInfo, path: str) -> dict:
    """What the restriction step is told about one image."""
    return {"file": path, "description": row.description, "record": row.record}


def _image_type(text: str) -> str:
    lowered = text.lower()
    if lowered in notes.IMAGE_TYPES:
        return lowered
    return next((kind for word, kind in _TYPE_WORDS if word in lowered), "")


def _from_name(path: str) -> str:
    return re.sub(r"[-_]+", " ", PurePosixPath(path).stem).strip().capitalize()


def _hash(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
