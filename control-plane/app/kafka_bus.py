# control_plane/kafka_bus.py (or wherever this lives)
from __future__ import annotations

import json
from typing import Any, Mapping, Optional

from aiokafka import AIOKafkaProducer

from common.ai_training_common.config import KAFKA_BOOTSTRAP, KAFKA_TOPIC
from common.ai_training_common.events import JobEventIn


producer: Optional[AIOKafkaProducer] = None


async def init_kafka() -> None:
    global producer
    if producer is not None:
        return

    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP.split(","),
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        linger_ms=20,
    )
    await producer.start()


async def close_kafka() -> None:
    global producer
    if producer is None:
        return
    await producer.stop()
    producer = None


async def send_event(event: JobEventIn | Mapping[str, Any]) -> None:
    """
    Publish a job event to Kafka using the canonical envelope (event_type only).

    - Accepts JobEventIn or a dict-like object that validates into JobEventIn.
    - Uses job_id as Kafka message key to preserve per-job ordering.
    """
    if producer is None:
        raise RuntimeError("Kafka producer not initialized (call init_kafka())")

    ev = event if isinstance(event, JobEventIn) else JobEventIn.model_validate(event)

    await producer.send_and_wait(
        KAFKA_TOPIC,
        value=ev.model_dump(),              # guaranteed event_type top-level
        key=ev.job_id.encode("utf-8"),      # per-job ordering
    )
