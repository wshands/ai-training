
import logging
import os
# Why put logging setup outside main()?
# Anything imported before you call setup_logging() might emit logs (or configure logging itself).
# Calling it at module import time ensures all logs (including early startup) use your format/level.
# In containers, the entrypoint module is the natural “one-time per process” place.
# force=True tells Python to remove any existing logging handlers and reconfigure
# logging with your settings. This is useful in container apps because frameworks
# (uvicorn/gunicorn) or imported libraries might configure logging before your code runs.
def setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True
    )

setup_logging()
logger = logging.getLogger(__name__)


from common.ai_training_common.events import JobEventIn, EventType
import os, json, time, sys, signal, asyncio
import torch
from aiokafka import AIOKafkaProducer
from typing import Any, Dict


terminate = False
def handle_sigterm(signum, frame):
    global terminate
    terminate = True
signal.signal(signal.SIGTERM, handle_sigterm)

JOB_CONFIG = os.environ.get("JOB_CONFIG", "/opt/job/config.json")
KAFKA = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
TOPIC = os.environ.get("KAFKA_TOPIC", "job-events")

# ---------- PRODUCER INIT ----------
producer: AIOKafkaProducer | None = None
current_seq: int = 0
PRODUCER_NAME = os.environ.get("PRODUCER_NAME", "training-job")

async def init_producer():
    global producer
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA.split(","),
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        request_timeout_ms=30000,
        retry_backoff_ms=500,
    )
    await producer.start()


async def emit(event_type: EventType, job_id: str, **kwargs: Any) -> None:
    global current_seq
    if producer is None:
        raise RuntimeError("Producer not initialized")

    if current_seq == 0:
        current_seq = int(kwargs.pop("_seq_start", 2))

    ev = JobEventIn.make(
        event_type=event_type,
        job_id=job_id,
        seq=current_seq,
        producer=PRODUCER_NAME,
        payload=dict(kwargs),
    )
    current_seq += 1

    try:
        meta = await producer.send_and_wait(
            TOPIC,
            value=ev.model_dump(),  # validated canonical envelope
            key=job_id.encode("utf-8"),
        )
        logger.info(f"sent job_id={job_id} event_type={event_type} "
            f"partition={meta.partition} offset={meta.offset}"
        )
    except Exception as e:
        logger.error(f"failed to send job event job_id={job_id} event_type={event_type}: {e}")
        raise


# ---------- TRAINING LOGIC ----------
def load_config():
    with open(JOB_CONFIG) as f:
        return json.load(f)


def build_model():
    import torch.nn as nn
    return nn.Sequential(
        nn.Linear(128,64),
        nn.ReLU(),
        nn.Linear(64,10)
    )


def build_data(batch_size, val_split=0.2, seed=42):
    import torch.utils.data as data
    gen = torch.Generator().manual_seed(seed)
    X = torch.randn(2000, 128, generator=gen)
    weights = torch.randn(10, 128, generator=gen)
    logits = X @ weights.T
    y = logits.argmax(dim=1)
    dataset = data.TensorDataset(X, y)
    val_size = int(len(dataset) * val_split)
    train_size = len(dataset) - val_size
    train_ds, val_ds = data.random_split(dataset, [train_size, val_size], generator=gen)
    train_loader = data.DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = data.DataLoader(val_ds, batch_size=batch_size, shuffle=False)
    return train_loader, val_loader


async def run_job():
    cfg = load_config()
    jid = cfg.get("job_id", f"job-{int(time.time())}")
    seq_start = int(cfg.get("seq_start", 2))

    await emit(EventType.JOB_STARTED, jid, _seq_start=seq_start)
    
    model = build_model()
    await emit(EventType.JOB_LOG, jid, level="INFO", message="Building synthetic dataset")
    val_split = float(cfg.get("val_split", 0.2))
    loader, val_loader = build_data(
        cfg.get("batch_size",32),
        val_split=val_split,
        seed=int(cfg.get("seed", 42)),
    )
    opt = torch.optim.Adam(model.parameters(), lr=cfg.get("lr",1e-3))
    epochs = cfg.get("epochs",1)
    fail_after_epoch = cfg.get("fail_after_epoch")

    await emit(EventType.JOB_LOG, jid, level="INFO", message="Training started")
    try:
        for e in range(epochs):
            if terminate:
                await emit(EventType.JOB_LOG, jid, level="WARNING", message="Cancellation requested")
                await emit(EventType.JOB_CANCELLED, jid, epoch=e)
                return 0
            
            # For testing failure handling
            if fail_after_epoch and (e + 1) >= int(fail_after_epoch):
                raise RuntimeError(f"forced failure at epoch {e + 1}")

            total = 0.0
            for X, y in loader:
                out = model(X)
                loss = torch.nn.functional.cross_entropy(out, y)
                opt.zero_grad()
                loss.backward()
                opt.step()
                total += loss.item()

            avg = total / len(loader)
            model.eval()
            correct = 0
            seen = 0
            with torch.no_grad():
                for X, y in val_loader:
                    out = model(X)
                    preds = out.argmax(dim=1)
                    correct += (preds == y).sum().item()
                    seen += y.numel()
            model.train()

            accuracy = (correct / seen) if seen else 0.0
            await emit(
                EventType.EPOCH_METRIC,
                jid,
                epoch=e + 1,
                metrics={"loss": avg, "accuracy": accuracy},
            )
            await emit(
                EventType.JOB_LOG,
                jid,
                level="INFO",
                message=f"Epoch {e+1}/{epochs} completed, loss={avg:.4f}, acc={accuracy:.4f}",
            )
            await asyncio.sleep(0.1)

    except Exception as ex:
        await emit(EventType.JOB_FAILED, jid, error={"message": str(ex), "type": type(ex).__name__})
        await emit(EventType.JOB_LOG, jid, level="ERROR", message=f"Job failed: {ex}")
        return 1

    await emit(EventType.JOB_COMPLETED, jid)
    await emit(EventType.JOB_LOG, jid, level="INFO", message="Training completed successfully")
    return 0


async def main():
    await init_producer()
    rc = await run_job()
    await producer.stop()
    return rc


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
