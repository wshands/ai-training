# common/ai_training_common/events.py
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ConfigDict


class EventType(str, Enum):
    JOB_SUBMITTED = "JOB_SUBMITTED"
    JOB_STARTED = "JOB_STARTED"
    JOB_LOG = "JOB_LOG"
    EPOCH_METRIC = "EPOCH_METRIC"
    JOB_METRIC = "JOB_METRIC"
    JOB_PREEMPTED = "JOB_PREEMPTED"
    JOB_CANCELLED = "JOB_CANCELLED"
    JOB_FAILED = "JOB_FAILED"
    JOB_COMPLETED = "JOB_COMPLETED"


class JobEventIn(BaseModel):
    """Canonical Kafka envelope (event_type everywhere)."""
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType
    job_id: str
    seq: int
    ts_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    producer: str
    payload: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def make(
        cls,
        *,
        event_type: EventType,
        job_id: str,
        seq: int,
        producer: str,
        payload: Optional[Dict[str, Any]] = None,
        schema_version: int = 1,
        ts_ms: Optional[int] = None,
        event_id: Optional[str] = None,
    ) -> "JobEventIn":
        return cls(
            schema_version=schema_version,
            event_id=event_id or str(uuid.uuid4()),
            event_type=event_type,
            job_id=job_id,
            seq=seq,
            ts_ms=ts_ms or int(time.time() * 1000),
            producer=producer,
            payload=payload or {},
        )

    def to_out(self, *, id: int, event_time: str, state: str) -> "JobEventOut":
        return JobEventOut(
            id=id,
            job_id=self.job_id,
            event_time=event_time,
            event_type=self.event_type,
            seq=self.seq,
            ts_ms=self.ts_ms,
            producer=self.producer,
            schema_version=self.schema_version,
            data=self.payload,
            state=state,
        )


class JobEventOut(BaseModel):
    """Redis/UI/REST shape."""
    model_config = ConfigDict(extra="forbid")

    id: int
    job_id: str
    event_time: str
    event_type: EventType
    seq: int
    ts_ms: int
    producer: str
    schema_version: int
    data: Dict[str, Any] = Field(default_factory=dict)
    state: str
