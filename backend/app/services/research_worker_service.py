"""Recoverable asyncio consumer for durable research compilation jobs."""

from __future__ import annotations

import asyncio
import os

from . import research_job_queue_service, research_service


def enabled() -> bool:
    return research_job_queue_service.worker_mode() == "background"


class ResearchWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop: asyncio.Event | None = None

    async def start(self) -> None:
        # Recovery is part of every application startup, including explicit
        # inline test mode, so no interrupted row remains permanently running.
        await asyncio.to_thread(research_job_queue_service.recover_running_jobs)
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
        task = self._task
        try:
            await asyncio.wait_for(
                task,
                timeout=max(
                    1.0,
                    float(os.environ.get("AI_TD_RESEARCH_WORKER_STOP_SECONDS", "10")),
                ),
            )
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        except Exception:
            # A failed background consumer must not prevent the remaining app
            # services from completing their own shutdown.
            pass
        finally:
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
            try:
                claimed = await asyncio.to_thread(research_job_queue_service.claim_next_job)
            except Exception:
                await self._sleep_or_stop(stop, interval)
                continue
            if claimed is not None:
                # The existing workflow runner is synchronous and filesystem
                # heavy; keep it entirely outside the event-loop thread.
                try:
                    await asyncio.to_thread(research_service.run_claimed_job, claimed)
                except Exception:
                    try:
                        await asyncio.to_thread(
                            research_job_queue_service.requeue_interrupted_job,
                            str(claimed["job_id"]),
                        )
                    except Exception:
                        pass
                    await self._sleep_or_stop(stop, interval)
                continue
            await self._sleep_or_stop(stop, interval)

    @staticmethod
    async def _sleep_or_stop(stop: asyncio.Event, interval: float) -> None:
        if stop.is_set():
            return
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass


worker = ResearchWorker()
