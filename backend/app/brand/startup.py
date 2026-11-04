"""Brand work done when the app starts: preload the settings folder, and finish interrupted reads."""

import logging

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
    source = str(folder.resolve())
    if brands.find_by_source(source):
        return
    log.info("Preloading the brand folder %s", source)
    try:
        name = settings.brand_name or folder.name
        brands.create(name, read_folder(folder), settings.brand_exclude_patterns, source=source)
    except NothingToRead as error:
        log.warning("Not preloading %s: %s", source, error)
