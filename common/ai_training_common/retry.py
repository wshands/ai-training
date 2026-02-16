"""Retry helpers for job scheduling."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Tuple


def compute_retry_delay_seconds(
    retry_count: int, base_seconds: int, max_seconds: int
) -> int:
    delay = base_seconds * (2 ** max(retry_count, 0))
    return int(min(delay, max_seconds))


def build_retry_job_config(
    cfg: Dict[str, Any],
    job_id: str,
    retry_count: int,
    details: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    if not isinstance(cfg, dict):
        raise ValueError("jobs.config must be a JSON object (dict)")

    new_job_id = str(uuid.uuid4())
    root_retry_of = cfg.get("retry_of") or job_id
    new_cfg = dict(cfg)
    new_cfg["job_id"] = new_job_id
    new_cfg["submitted_at"] = int(time.time())
    new_cfg["seq_start"] = 2
    new_cfg["retry_of"] = root_retry_of
    new_cfg["retry_attempt"] = retry_count + 1
    if "retry_reason" not in new_cfg:
        new_cfg["retry_reason"] = details.get("error") or {"message": "auto-retry"}

    return new_job_id, new_cfg
