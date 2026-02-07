"""Event bus abstraction for control-plane job events (Kafka or SQS)."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Mapping, Optional

import boto3
from aiokafka import AIOKafkaProducer

from common.ai_training_common.config import (
    EVENT_BUS_PROVIDER,
    KAFKA_TOPIC,
    SQS_ENDPOINT_URL,
    SQS_QUEUE_URL,
)
from common.ai_training_common.events import JobEventIn
from common.ai_training_common.kafka import build_kafka_config


_kafka_producer: Optional[AIOKafkaProducer] = None
_sqs_client = None
_sqs_queue_url = ""


async def init_event_bus() -> None:
    """Initialize the event bus client based on EVENT_BUS_PROVIDER."""
    provider = EVENT_BUS_PROVIDER
    if provider == "kafka":
        await _init_kafka()
        return
    if provider == "sqs":
        _init_sqs()
        return
    raise ValueError(f"Unsupported EVENT_BUS_PROVIDER: {provider}")


async def close_event_bus() -> None:
    """Close the event bus client when applicable."""
    provider = EVENT_BUS_PROVIDER
    if provider == "kafka":
        await _close_kafka()


async def send_event(event: JobEventIn | Mapping[str, Any]) -> None:
    """
    Publish a job event to the configured event bus.

    Kafka: uses job_id as the message key for per-job ordering.
    SQS FIFO: uses job_id as MessageGroupId and event_id as deduplication id.
    """
    ev = event if isinstance(event, JobEventIn) else JobEventIn.model_validate(event)
    if not ev.job_id:
        raise ValueError("Job event is missing job_id")

    provider = EVENT_BUS_PROVIDER
    if provider == "kafka":
        await _send_kafka(ev)
        return
    if provider == "sqs":
        await _send_sqs(ev)
        return
    raise ValueError(f"Unsupported EVENT_BUS_PROVIDER: {provider}")


async def _init_kafka() -> None:
    """Initialize the shared Kafka producer."""
    global _kafka_producer
    if _kafka_producer is not None:
        return

    kafka_config = build_kafka_config()
    kafka_config["value_serializer"] = lambda v: json.dumps(v).encode("utf-8")
    kafka_config["linger_ms"] = 20
    _kafka_producer = AIOKafkaProducer(**kafka_config)
    await _kafka_producer.start()


async def _close_kafka() -> None:
    """Stop and clear the shared Kafka producer."""
    global _kafka_producer
    if _kafka_producer is None:
        return
    await _kafka_producer.stop()
    _kafka_producer = None


async def _send_kafka(ev: JobEventIn) -> None:
    if _kafka_producer is None:
        raise RuntimeError("Kafka producer not initialized (call init_event_bus())")
    await _kafka_producer.send_and_wait(
        KAFKA_TOPIC,
        value=ev.model_dump(),
        key=ev.job_id.encode("utf-8"),
    )


def _init_sqs() -> None:
    global _sqs_client, _sqs_queue_url
    if _sqs_client is not None:
        return
    if not SQS_QUEUE_URL:
        raise RuntimeError("SQS_QUEUE_URL is required when EVENT_BUS_PROVIDER=sqs")
    kwargs = {}
    if SQS_ENDPOINT_URL:
        kwargs["endpoint_url"] = SQS_ENDPOINT_URL
    _sqs_client = boto3.client("sqs", **kwargs)
    _sqs_queue_url = SQS_QUEUE_URL


async def _send_sqs(ev: JobEventIn) -> None:
    if _sqs_client is None:
        raise RuntimeError("SQS client not initialized (call init_event_bus())")
    payload = ev.model_dump()
    await asyncio.to_thread(
        _sqs_client.send_message,
        QueueUrl=_sqs_queue_url,
        MessageBody=json.dumps(payload),
        MessageGroupId=ev.job_id,
        MessageDeduplicationId=ev.event_id,
    )
