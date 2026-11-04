from dataclasses import dataclass

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.ai.models import AiCall
from app.ai.transport import AiTransport
from app.brand import cards
from app.brand import files as brand_files
from app.brand.files import IncomingFile
from app.brand.models import Brand, BrandDecision, BrandFile
from app.brand.parsing import decode
from app.brand.reader import BrandReader
from app.brand.settle import settle
from app.config import Settings
from app.jobs import JobRunner


class BrandNotFound(Exception):
    pass


class AlreadyReading(Exception):
    """A read or summary rebuild of this brand is already running."""


class NothingToRead(ValueError):
    pass


class BadCorrection(ValueError):
    pass


CORRECTION_VALUES: dict[str, tuple[str, ...]] = {
    "document_status": ("current", "replaced", "draft", "archived"),
    "document_kind": tuple(cards.KINDS),
    "conflict_winner": (),  # any document path; checked when the conflict is judged
    "image_usable": ("yes", "no"),
}


def _usable(incoming: list[IncomingFile], exclude: list[str]) -> list[IncomingFile]:
    """Cleans paths, drops the folder's own name, and leaves out hidden and excluded files."""
    kept = brand_files.strip_common_root([IncomingFile(brand_files.clean_path(f.path), f.content) for f in incoming])
    return [f for f in kept if not brand_files.is_hidden(f.path) and not brand_files.is_excluded(f.path, exclude)]


@dataclass(frozen=True)
class ReadingCost:
    usd: float
    calls: int
    tokens_in: int
    tokens_out: int


class BrandService:
    def __init__(
        self,
        session: Session,
        sessions: sessionmaker[Session],
        transport: AiTransport,
        settings: Settings,
        jobs: JobRunner,
    ) -> None:
        self._session = session
        self._reader = BrandReader(sessions, transport, settings)
        self._settings = settings
        self._jobs = jobs

    def create(
        self, name: str, incoming: list[IncomingFile], exclude: list[str], source: str | None = None
    ) -> Brand:
        """Stores the brand's files and starts reading them in the background."""
        kept = _usable(incoming, exclude)
        if not any(brand_files.kind_of(f.path) == "document" for f in kept):
            raise NothingToRead("The folder has no text documents (.md, .markdown or .txt) to read.")
        brand = Brand(name=name.strip() or "Brand", source=source)
        self._session.add(brand)
        self._session.flush()
        self._store(brand, kept)
        self.resume_reading(brand.id)
        return brand

    def add_files(self, brand_id: int, incoming: list[IncomingFile], exclude: list[str]) -> Brand:
        """Adds new files and replaces changed ones, then reads again. Unchanged files keep their work."""
        brand = self.get(brand_id)
        kept = _usable(incoming, exclude)
        if not kept:
            raise NothingToRead("None of the chosen files can be used.")
        self._claim(brand_id)
        self._store(brand, kept)
        self.resume_reading(brand.id)
        return brand

    def _store(self, brand: Brand, incoming: list[IncomingFile]) -> None:
        existing = {f.path: f for f in brand.files}
        for incoming_file in incoming:
            sha = brand_files.sha256_of(incoming_file.content)
            current = existing.get(incoming_file.path)
            if current and current.sha256 == sha:
                continue
            kind = brand_files.kind_of(incoming_file.path)
            target = brand_files.storage_path(self._settings.data_dir, brand.id, incoming_file.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(incoming_file.content)
            stored = current or BrandFile(path=incoming_file.path)
            stored.kind, stored.size_bytes, stored.sha256 = kind, len(incoming_file.content), sha
            stored.text = decode(incoming_file.content) if kind == "document" else None
            if current is None:
                brand.files.append(stored)
        self._session.commit()

    def correct(self, brand_id: int, kind: str, target: str, value: str) -> None:
        """Saves a correction and applies it at once. A newer correction of the same thing replaces the older one."""
        self.get(brand_id)
        save_correction(self._session, brand_id, kind, target, value)

    def undo_correction(self, brand_id: int, decision_id: int) -> None:
        self._session.execute(
            delete(BrandDecision).where(BrandDecision.brand_id == brand_id, BrandDecision.id == decision_id)
        )
        self._session.commit()
        settle(self._session, brand_id)

    def decisions(self, brand_id: int) -> list[BrandDecision]:
        return list(
            self._session.scalars(select(BrandDecision).where(BrandDecision.brand_id == brand_id).order_by(BrandDecision.id))
        )

    def edit_summary(self, brand_id: int, text: str) -> Brand:
        brand = self.get(brand_id)
        brand.summary, brand.summary_edited, brand.summary_stale = text, True, False
        self._session.commit()
        return brand

    def rebuild_summary(self, brand_id: int) -> None:
        brand = self.get(brand_id)
        self._claim(brand_id)
        self._session.commit()
        self._jobs.submit(lambda: self._reader.rebuild_summary(brand_id))
        self._session.refresh(brand)

    def start_reading(self, brand_id: int) -> None:
        self.get(brand_id)
        self._claim(brand_id)
        self.resume_reading(brand_id)

    def resume_reading(self, brand_id: int) -> None:
        """Reads a brand already marked as reading: a new brand, new files, or a read cut off by a restart."""
        brand = self.get(brand_id)
        self._session.commit()
        self._jobs.submit(lambda: self._reader.read(brand_id))
        self._session.refresh(brand)

    def _claim(self, brand_id: int) -> None:
        """Marks the brand as reading, in one step that only one request can win, so two reads never overlap."""
        claimed = self._session.execute(
            update(Brand).where(Brand.id == brand_id, Brand.status != "reading").values(status="reading")
        ).rowcount
        if claimed == 0:
            self._session.rollback()
            raise AlreadyReading("This brand is already being read. Wait for it to finish, then try again.")

    def list(self) -> list[Brand]:
        return list(self._session.scalars(select(Brand).order_by(Brand.id.desc())))

    def get(self, brand_id: int) -> Brand:
        brand = self._session.get(Brand, brand_id)
        if brand is None:
            raise BrandNotFound(brand_id)
        return brand

    def find_by_source(self, source: str) -> Brand | None:
        return self._session.scalars(select(Brand).where(Brand.source == source)).first()

    def mark_reviewed(self, brand_id: int) -> Brand:
        brand = self.get(brand_id)
        brand.reviewed = True
        self._session.commit()
        return brand

    def reading_cost(self, brand_id: int) -> ReadingCost:
        usd, calls, tokens_in, tokens_out = self._session.execute(
            select(
                func.coalesce(func.sum(AiCall.cost_usd), 0.0),
                func.count(AiCall.id),
                func.coalesce(func.sum(AiCall.tokens_in), 0),
                func.coalesce(func.sum(AiCall.tokens_out), 0),
            ).where(AiCall.brand_id == brand_id, AiCall.chat_id.is_(None))
        ).one()
        return ReadingCost(usd=usd, calls=calls, tokens_in=tokens_in, tokens_out=tokens_out)


def save_correction(session: Session, brand_id: int, kind: str, target: str, value: str) -> None:
    allowed = CORRECTION_VALUES.get(kind)
    if allowed is None or (allowed and value not in allowed):
        raise BadCorrection(f"Can't set {kind} to {value!r}.")
    session.execute(
        delete(BrandDecision).where(
            BrandDecision.brand_id == brand_id, BrandDecision.kind == kind, BrandDecision.target == target
        )
    )
    session.add(BrandDecision(brand_id=brand_id, kind=kind, target=target, value=value))
    session.commit()
    settle(session, brand_id)
