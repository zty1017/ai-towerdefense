#!/usr/bin/env python3
"""Shared status constants for WorkerTaskPack acceptance reports."""

from __future__ import annotations


from tools.dev.report_status_contract import (
    REPORT_VALID_STATUSES,
    STATUS_DRY_RUN,
    STATUS_FAILED,
    STATUS_PASSED,
)


WORKER_ACCEPTANCE_VALID_STATUSES = REPORT_VALID_STATUSES
