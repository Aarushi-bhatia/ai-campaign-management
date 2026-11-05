import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from app.ai.deps import get_ai_transport
from app.brand.routes import router as brand_router
from app.brand.startup import on_startup
from app.calls.routes import router as calls_router
from app.chat.routes import router as chat_router
from app.campaign.runtime import Runtime
from app.campaign.writing.queue import resume_interrupted
from app.config import get_settings
from app.db import SessionLocal
from app.memory.routes import router as memory_router
from app.jobs import get_job_runner
from app.research.deps import get_web_research

logging.basicConfig(level=logging.INFO)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        def resolve(dependency):
            """Startup uses the same dependencies as requests, so tests can swap them."""
            return app.dependency_overrides.get(dependency, dependency)()

        settings, transport, jobs = resolve(get_settings), resolve(get_ai_transport), resolve(get_job_runner)
        await run_in_threadpool(on_startup, settings, transport, jobs)
        runtime = Runtime(SessionLocal, transport, settings, jobs, resolve(get_web_research))
        await run_in_threadpool(resume_interrupted, runtime)
        yield

    app = FastAPI(title="Campaign agent", lifespan=lifespan)
    app.include_router(chat_router)
    app.include_router(brand_router)
    app.include_router(calls_router)
    app.include_router(memory_router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
