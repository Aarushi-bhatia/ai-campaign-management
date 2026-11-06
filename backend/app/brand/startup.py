"""Brand work done when the app starts: preload the settings folder, and finish interrupted reads."""

import logging
from pathlib import Path

from sqlalchemy import select

from app.ai.transport import AiTransport
from app.brand.files import read_folder
from app.brand.models import Brand
from app.brand.service import BrandService, NothingToRead
from app.config import Settings
from app.db import SessionLocal
from app.jobs import JobRunner

log = logging.getLogger(__name__)


def on_startup(settings: Settings, transport: AiTransport, jobs: JobRunner) -> None:
    with SessionLocal() as session:
        brands = BrandService(session, SessionLocal, transport, settings, jobs)
        for brand_id in session.scalars(select(Brand.id).where(Brand.status == "reading")):
            log.info("Resuming the interrupted read of brand %s", brand_id)
            brands.resume_reading(brand_id)
        _preload(brands, settings)


def _preload(brands: BrandService, settings: Settings) -> None:
    folder = settings.brand_dir
    if folder is None or not folder.is_dir() or not any(folder.iterdir()):
        return
    # Inside Docker the folder is always mounted at the same place, so the folder as named on the machine tells
    # brands apart. A brand preloaded before that was known (its source is the mount) counts as loaded: reading
    # it again unasked would cost a full brand read.
    source = f"folder:{settings.brand_source.strip()}" if settings.brand_source.strip() else str(folder.resolve())
    if brands.find_by_source(source) or (source != str(folder.resolve())
                                         and brands.find_by_source(str(folder.resolve()))):
        return
    log.info("Preloading the brand folder %s", source)
    try:
        name = settings.brand_name or (Path(settings.brand_source.strip()).name if settings.brand_source.strip()
                                       else folder.name)
        brands.create(name, read_folder(folder), settings.brand_exclude_patterns, source=source)
    except NothingToRead as error:
        log.warning("Not preloading %s: %s", source, error)
