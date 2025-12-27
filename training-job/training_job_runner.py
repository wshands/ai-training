#!/usr/bin/env python3
import os, json, time, sys, signal, asyncio
import torch
from aiokafka import AIOKafkaProducer

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

async def init_producer():
    global producer
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA.split(","),
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        request_timeout_ms=30000,
        retry_backoff_ms=500,
    )
    await producer.start()


async def emit(event_type, job_id, **kwargs):
    if producer is None:
        raise RuntimeError("Producer not initialized")

    event = {
        "type": event_type,
        "job_id": job_id,
        "timestamp": int(time.time()),
        **kwargs,
    }

    try:
        await producer.send_and_wait(TOPIC, event)
    except Exception as e:
        print("kafka send failed", e, flush=True)



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

def build_data(batch_size):
    import torch.utils.data as data
    X = torch.randn(1000,128)
    y = torch.randint(0,10,(1000,))
    return data.DataLoader(data.TensorDataset(X,y), batch_size=batch_size, shuffle=True)


async def run_job():
    cfg = load_config()
    jid = cfg.get("job_id", f"job-{int(time.time())}")

    await emit("JOB_STARTED", jid)
    
    model = build_model()
    await emit("JOB_LOG", jid, message="Building synthetic dataset")
    loader = build_data(cfg.get("batch_size",32))
    opt = torch.optim.Adam(model.parameters(), lr=cfg.get("lr",1e-3))
    epochs = cfg.get("epochs",1)

    await emit("JOB_LOG", jid, message="Training started")
    try:
        for e in range(epochs):
            if terminate:
                await emit("JOB_LOG", jid, message="Preempting job")
                await emit("JOB_PREEMPTED", jid, epoch=e)
                return 0

            total = 0.0
            for X, y in loader:
                out = model(X)
                loss = torch.nn.functional.cross_entropy(out, y)
                opt.zero_grad()
                loss.backward()
                opt.step()
                total += loss.item()

            avg = total / len(loader)
            await emit("EPOCH_METRIC", jid, epoch=e, loss=avg)
            await emit("JOB_LOG", jid, message=f"Epoch {e+1}/{epochs} completed, loss={avg:.4f}")
            await asyncio.sleep(0.1)

    except Exception as ex:
        await emit("JOB_FAILED", jid, error=str(ex))
        await emit("JOB_LOG", jid, message=f"Job failed: {ex}")
        return 1

    await emit("JOB_COMPLETED", jid)
    await emit("JOB_LOG", jid, message="Training completed successfully")
    return 0


async def main():
    await init_producer()
    rc = await run_job()
    await producer.stop()
    return rc


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
