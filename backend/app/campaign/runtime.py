from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from app.ai.service import AiService
from app.ai.transport import AiTransport
from app.config import Settings
from app.jobs import JobRunner
from app.research.client import WebResearch


@dataclass(frozen=True)
class Runtime:
    """What background work needs: it opens its own database sessions, so it can't borrow a request's."""

    sessions: sessionmaker[Session]
    transport: AiTransport
    settings: Settings
    jobs: JobRunner
    web: WebResearch | None

    def ai(self, session: Session) -> AiService:
        return AiService(session, self.transport, self.settings, log_sessions=self.sessions)
