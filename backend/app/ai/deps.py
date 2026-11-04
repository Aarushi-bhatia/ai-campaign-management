from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.ai.service import AiService
from app.ai.transport import AiTransport, OpenAiTransport
from app.config import Settings, get_settings
from app.db import SessionLocal, get_session


@lru_cache
def get_ai_transport() -> AiTransport:
    """One OpenAI client for the whole app. Tests override this dependency with a fake."""
    return OpenAiTransport(api_key=get_settings().openai_api_key)


def get_ai_service(
    session: Annotated[Session, Depends(get_session)],
    transport: Annotated[AiTransport, Depends(get_ai_transport)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AiService:
    return AiService(session, transport, settings, log_sessions=SessionLocal)
