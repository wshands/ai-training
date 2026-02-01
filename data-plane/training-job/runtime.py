"""Shared runtime utilities for training jobs (platform-owned)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
from typing import Any, Awaitable, Callable, Dict

import httpx

from common.ai_training_common.config import (
    CONTROL_PLANE_URL,
    DATA_PLANE_API_TOKEN,
    DATA_PLANE_TENANT_ID,
    DEFAULT_TENANT_ID,
    DEFAULT_USER_ID,
)
from common.ai_training_common.events import EventType, JobEventIn


JOB_CONFIG_PATH = os.environ.get("JOB_CONFIG", "/opt/job/config.json")
PRODUCER_NAME = os.environ.get("PRODUCER_NAME", "training-job")

_terminate = False


def setup_logging() -> None:
    """Configure process-wide logging with an env-driven log level."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )


def _handle_sigterm(signum: int, frame: Any) -> None:
    """Handle SIGTERM by setting a termination flag."""
    global _terminate
    _terminate = True


signal.signal(signal.SIGTERM, _handle_sigterm)
logger = logging.getLogger(__name__)


def should_terminate() -> bool:
    """Return True if a termination signal was received."""
    return _terminate


def _data_plane_headers() -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if DATA_PLANE_API_TOKEN:
        headers["Authorization"] = f"Bearer {DATA_PLANE_API_TOKEN}"
    if DATA_PLANE_TENANT_ID:
        headers["X-Tenant-Id"] = DATA_PLANE_TENANT_ID
    return headers


class EventSink:
    """Send job events over HTTP to the control-plane."""

    def __init__(self) -> None:
        self._http_client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if not CONTROL_PLANE_URL:
            raise RuntimeError("CONTROL_PLANE_URL is required for HTTP event sink")
        self._http_client = httpx.AsyncClient(base_url=CONTROL_PLANE_URL.rstrip("/"))

    async def send(self, event: JobEventIn, job_id: str) -> None:
        if self._http_client is None:
            raise RuntimeError("HTTP client not initialized")
        resp = await self._http_client.post(
            "/internal/events",
            json=event.model_dump(),
            headers=_data_plane_headers(),
            timeout=10.0,
        )
        resp.raise_for_status()

    async def close(self) -> None:
        if self._http_client:
            await self._http_client.aclose()


class JobReporter:
    """Emit training lifecycle events with a monotonically increasing seq."""

    def __init__(
        self,
        sink: EventSink,
        job_id: str,
        tenant_id: str,
        user_id: str,
        seq_start: int,
    ) -> None:
        self._sink = sink
        self._job_id = job_id
        self._tenant_id = tenant_id
        self._user_id = user_id
        self._seq = seq_start
        self._terminal_sent = False

    @property
    def terminal_sent(self) -> bool:
        return self._terminal_sent

    async def emit(self, event_type: EventType, **payload: Any) -> None:
        event = JobEventIn.make(
            event_type=event_type,
            job_id=self._job_id,
            tenant_id=self._tenant_id,
            user_id=self._user_id,
            seq=self._seq,
            producer=PRODUCER_NAME,
            payload=dict(payload),
        )
        self._seq += 1
        await self._sink.send(event, self._job_id)

    async def started(self) -> None:
        await self.emit(EventType.JOB_STARTED)

    async def log(self, level: str, message: str) -> None:
        await self.emit(EventType.JOB_LOG, level=level, message=message)

    async def epoch_metric(self, epoch: int, metrics: Dict[str, Any]) -> None:
        await self.emit(EventType.EPOCH_METRIC, epoch=epoch, metrics=metrics)

    async def failed(self, message: str, error_type: str | None = None) -> None:
        if self._terminal_sent:
            return
        self._terminal_sent = True
        await self.emit(
            EventType.JOB_FAILED,
            error={"message": message, "type": error_type},
        )

    async def completed(self) -> None:
        if self._terminal_sent:
            return
        self._terminal_sent = True
        await self.emit(EventType.JOB_COMPLETED)

    async def cancelled(self, epoch: int | None = None) -> None:
        if self._terminal_sent:
            return
        self._terminal_sent = True
        payload = {"epoch": epoch} if epoch is not None else {}
        await self.emit(EventType.JOB_CANCELLED, **payload)


def load_job_config() -> Dict[str, Any]:
    """Load the job configuration JSON from disk."""
    with open(JOB_CONFIG_PATH) as f:
        return json.load(f)


async def run_training_job(
    train_fn: Callable[[Dict[str, Any], JobReporter, Callable[[], bool]], Awaitable[int]]
) -> int:
    """Run the customer-provided training function with platform reporting."""
    cfg = load_job_config()
    job_id = cfg.get("job_id", f"job-{int(time.time())}")
    seq_start = int(cfg.get("seq_start", 2))
    tenant_id = cfg.get("tenant_id") or DEFAULT_TENANT_ID
    user_id = cfg.get("user_id") or DEFAULT_USER_ID

    sink = EventSink()
    await sink.start()
    reporter = JobReporter(sink, job_id, tenant_id, user_id, seq_start)

    try:
        await reporter.started()
        rc = await train_fn(cfg, reporter, should_terminate)
        if should_terminate() and not reporter.terminal_sent:
            await reporter.cancelled()
            rc = 0
        elif rc == 0 and not reporter.terminal_sent:
            await reporter.completed()
        elif rc != 0 and not reporter.terminal_sent:
            await reporter.failed("training exited with non-zero status")
        return rc
    except Exception as exc:
        await reporter.failed(str(exc), type(exc).__name__)
        return 1
    finally:
        await sink.close()
