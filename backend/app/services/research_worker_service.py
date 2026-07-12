"""Recoverable asyncio consumer for durable research compilation jobs."""

from __future__ import annotations

import asyncio
import os

from . import research_service


def enabled() -> bool:
    return research_service.research_worker_mode() == "background"


class ResearchWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop: asyncio.Event | None = None

    async def start(self) -> None:
        # Recovery is part of every application startup, including explicit
        # inline test mode, so no interrupted row remains permanently running.
        await asyncio.to_thread(research_service.recover_running_jobs)
        if not enabled() or self._task is not None:
            return
        # A FastAPI app can be started again on a fresh event loop in tests or
        # embedding hosts. asyncio primitives must be created on that loop.
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="research-worker")

    async def stop(self) -> None:
        if self._task is None:
            return
        assert self._stop is not None
        self._stop.set()
        await self._task
        self._task = None
        self._stop = None

    async def _run(self) -> None:
        assert self._stop is not None
        stop = self._stop
        interval = max(
            0.05,
            float(os.environ.get("AI_TD_RESEARCH_WORKER_POLL_SECONDS", "0.25")),
        )
        while not stop.is_set():
            claimed = await asyncio.to_thread(research_service.claim_next_job)
            if claimed is not None:
                # The existing workflow runner is synchronous and filesystem
                # heavy; keep it entirely outside the event-loop thread.
                await asyncio.to_thread(research_service.run_claimed_job, claimed)
                continue
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except TimeoutError:
                pass


worker = ResearchWorker()
