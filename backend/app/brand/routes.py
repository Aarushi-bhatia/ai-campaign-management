from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.ai.deps import get_ai_transport
from app.ai.transport import AiTransport
from app.brand.files import IncomingFile, UnsafePath
from app.ai.deps import get_ai_service
from app.ai.service import AiCallFailed, AiService
from app.brand.files import storage_path
from app.brand.images.library import pick
from app.brand.images.picking import AssetSpec
from app.brand.schemas import (
    BlockedOut, BrandOut, BrandSummary, ChoiceOut, CorrectionIn, PickIn, PickOut, SummaryIn,
)
from app.brand.views import file_url
from app.brand.service import AlreadyReading, BadCorrection, BrandNotFound, BrandService, NothingToRead
from app.brand.views import brand_view
from app.config import Settings, get_settings
from app.db import SessionLocal, get_session
from app.jobs import JobRunner, get_job_runner

router = APIRouter(prefix="/api/brands", tags=["brands"])


def get_brand_service(
    session: Annotated[Session, Depends(get_session)],
    transport: Annotated[AiTransport, Depends(get_ai_transport)],
    settings: Annotated[Settings, Depends(get_settings)],
    jobs: Annotated[JobRunner, Depends(get_job_runner)],
) -> BrandService:
    return BrandService(session, SessionLocal, transport, settings, jobs)


Brands = Annotated[BrandService, Depends(get_brand_service)]
SessionDep = Annotated[Session, Depends(get_session)]
Uploads = Annotated[list[UploadFile], File()]
Exclude = Annotated[list[str], Form()]


async def _incoming(files: list[UploadFile]) -> list[IncomingFile]:
    """Each uploaded file's name is its path inside the brand folder."""
    return [IncomingFile(upload.filename or "", await upload.read()) for upload in files]


def _brand_or_404(brands: BrandService, brand_id: int):
    try:
        return brands.get(brand_id)
    except BrandNotFound:
        raise HTTPException(404, "Brand not found")


@router.get("", response_model=list[BrandSummary])
def list_brands(brands: Brands):
    return brands.list()


@router.post("", response_model=BrandSummary, status_code=201)
async def add_brand(brands: Brands, name: Annotated[str, Form()], files: Uploads, exclude: Exclude = []):  # noqa: B006
    """Upload a brand folder, and start reading it."""
    incoming = await _incoming(files)
    try:
        return await run_in_threadpool(brands.create, name, incoming, exclude)
    except (UnsafePath, NothingToRead) as error:
        raise HTTPException(400, str(error))


@router.get("/{brand_id}", response_model=BrandOut)
def get_brand(brand_id: int, brands: Brands, session: SessionDep):
    return brand_view(session, brands, _brand_or_404(brands, brand_id))


@router.post("/{brand_id}/files", response_model=BrandSummary)
async def update_brand(brand_id: int, brands: Brands, files: Uploads, exclude: Exclude = []):  # noqa: B006
    """Upload the brand folder again. Only new or changed files are read."""
    _brand_or_404(brands, brand_id)
    incoming = await _incoming(files)
    try:
        return await run_in_threadpool(brands.add_files, brand_id, incoming, exclude)
    except (UnsafePath, NothingToRead) as error:
        raise HTTPException(400, str(error))
    except AlreadyReading as error:
        raise HTTPException(409, str(error))


@router.post("/{brand_id}/read", response_model=BrandSummary)
def read_again(brand_id: int, brands: Brands):
    """Reads the brand again. Unchanged documents keep their sections, cards and facts."""
    _brand_or_404(brands, brand_id)
    try:
        brands.start_reading(brand_id)
    except AlreadyReading as error:
        raise HTTPException(409, str(error))
    return brands.get(brand_id)


@router.post("/{brand_id}/reviewed", response_model=BrandSummary)
def mark_reviewed(brand_id: int, brands: Brands):
    _brand_or_404(brands, brand_id)
    return brands.mark_reviewed(brand_id)


@router.post("/{brand_id}/corrections", response_model=BrandOut)
def correct(brand_id: int, body: CorrectionIn, brands: Brands, session: SessionDep):
    """Correct a document's status or type, or pick a conflict's winner. Applies at once, without AI."""
    brand = _brand_or_404(brands, brand_id)
    try:
        brands.correct(brand_id, body.kind, body.target, body.value)
    except BadCorrection as error:
        raise HTTPException(400, str(error))
    session.refresh(brand)
    return brand_view(session, brands, brand)


@router.delete("/{brand_id}/corrections/{decision_id}", response_model=BrandOut)
def undo_correction(brand_id: int, decision_id: int, brands: Brands, session: SessionDep):
    brand = _brand_or_404(brands, brand_id)
    brands.undo_correction(brand_id, decision_id)
    session.refresh(brand)
    return brand_view(session, brands, brand)


@router.put("/{brand_id}/summary", response_model=BrandSummary)
def edit_summary(brand_id: int, body: SummaryIn, brands: Brands):
    """Save the user's own version of the summary. It is kept until they ask for a rebuild."""
    _brand_or_404(brands, brand_id)
    return brands.edit_summary(brand_id, body.text)


@router.post("/{brand_id}/summary/rebuild", response_model=BrandSummary)
def rebuild_summary(brand_id: int, brands: Brands):
    _brand_or_404(brands, brand_id)
    try:
        brands.rebuild_summary(brand_id)
    except AlreadyReading as error:
        raise HTTPException(409, str(error))
    return brands.get(brand_id)


@router.get("/{brand_id}/files/{path:path}")
def brand_file(brand_id: int, path: str, brands: Brands, settings: Annotated[Settings, Depends(get_settings)]):
    """Serves an image from the brand folder, so the app can show it."""
    brand = _brand_or_404(brands, brand_id)
    if not any(f.path == path and f.kind == "image" for f in brand.files):
        raise HTTPException(404, "Image not found")
    return FileResponse(storage_path(settings.data_dir, brand_id, path), headers=FILE_HEADERS)


FILE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    # An uploaded SVG is a document that can hold scripts, and it is served on the app's own address. Opened
    # directly, it runs nothing and loads nothing; shown in an <img> tag, as the app does, it looks the same.
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox",
}


@router.post("/{brand_id}/images/pick", response_model=PickOut)
def pick_images(
    brand_id: int, body: PickIn, brands: Brands, session: SessionDep, ai: Annotated[AiService, Depends(get_ai_service)]
):
    """Picks images for one asset: blocks what can't be used, then ranks the rest."""
    brand = _brand_or_404(brands, brand_id)
    spec = AssetSpec(
        channel=body.channel, asset_type=body.asset_type, message=body.message, slot=body.slot,
        campaign_rules=body.campaign_rules, exclude_paths=frozenset(body.exclude),
    )
    try:
        result = pick(session, ai, brand, spec)
    except AiCallFailed as failure:
        raise HTTPException(502, f"The AI request failed: {failure}")
    return PickOut(
        choices=[ChoiceOut(path=c.path, url=file_url(brand_id, c.path), why=c.why, alt_text=c.alt_text) for c in result.choices],
        suggestion=result.suggestion,
        blocked=[BlockedOut(path=b.path, reason=b.reason) for b in result.blocked],
        call_id=result.call_id,
    )
