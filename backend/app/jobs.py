"""Runs long work, such as reading a brand, outside the request that started it."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Protocol

log = logging.getLogger(__name__)


class JobRunner(Protocol):
    def submit(self, job: Callable[[], None]) -> None: ...


class ThreadJobRunner:
    def __init__(self, workers: int = 2) -> None:
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job")

    def submit(self, job: Callable[[], None]) -> None:
        self._pool.submit(self._run, job)

    @staticmethod
    def _run(job: Callable[[], None]) -> None:
        try:
            job()
        except Exception:
            log.exception("Background job failed")


class InlineJobRunner:
    """Runs the job straight away. Used in tests, so results can be checked right after the request."""

    def submit(self, job: Callable[[], None]) -> None:
        job()


@lru_cache
def get_job_runner() -> JobRunner:
    return ThreadJobRunner()
