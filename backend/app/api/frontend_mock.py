"""Compatibility aggregator for the frontend mock API routers.

The original ``frontend_mock`` module mixed scheduler, gameplay, and shared
helpers. Those responsibilities now live in ``generation_scheduler``,
``gameplay_runtime``, and ``_frontend_runtime_common``. This module keeps the
``frontend_mock_api.router`` symbol that ``main.py`` includes, re-exporting the
union of the split routers unchanged.
"""

from __future__ import annotations

from fastapi import APIRouter

from .gameplay_runtime import router as gameplay_runtime_router
from .generation_scheduler import router as generation_scheduler_router

router = APIRouter()
router.include_router(generation_scheduler_router)
router.include_router(gameplay_runtime_router)
