import json
from aiokafka import AIOKafkaProducer
from .config import KAFKA_BOOTSTRAP, KAFKA_TOPIC

producer: AIOKafkaProducer | None = None

async def init_kafka():
    global producer
    if producer is None:
        producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP.split(","),
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            linger_ms=20,
        )
        await producer.start()

async def send_event(event: dict):
    if producer is None:
        raise RuntimeError("Kafka producer not initialized")
    await producer.send_and_wait(KAFKA_TOPIC, event)
