
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

import uuid
import time
import json
import redis.asyncio as redis

from datetime import datetime
from enum import Enum
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocket, WebSocketDisconnect
from kubernetes import client, config as k8s_config
from pydantic import BaseModel, Field, ValidationError
from typing import Any, Dict, List, Optional

#from fastapi import WebSocket
from common.ai_training_common.config import (
    TRAINING_NAMESPACE,
    TRAINING_IMAGE,
    CUSTOMER_KUBECONFIG,
    REDIS_URL,
)
from .kafka_bus import init_kafka, send_event
from common.ai_training_common.db import (
    init_db,
    persist_initial_job,
    fetch_jobs,
    fetch_job_events_since,
    fetch_job_event_types_until,
    fetch_job,
)
from common.ai_training_common.events import JobEventIn, JobEventOut, EventType
from common.ai_training_common.state_machine import JobState as EventJobState, apply_event


class JobState(str, Enum):
    SUBMITTED = "SUBMITTED"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PREEMPTED = "PREEMPTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"
    COMPLETED = "COMPLETED"


class JobSummary(BaseModel):
    job_id: str
    status: JobState = JobState.UNKNOWN
    created_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    model_id: Optional[str] = None
    dataset_id: Optional[str] = None

app = FastAPI(title="AI Platform Control Plane")

# Configure CORS
origins = [
    "http://localhost",        # Allow requests from localhost without a port (default port 80)
    "http://localhost:3000",   # Your frontend application's origin
    # Add any other origins where your frontend might be hosted, e.g.,
    # "https://your-frontend-domain.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for prod
    #allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TrainJobRequest(BaseModel):
    model_id: str
    dataset_id: str
    epochs: int = 1
    batch_size: int = 32
    lr: float = 1e-3
    distributed: bool = False
    extra_config: dict | None = None


def load_k8s_clients():
    k8s_config.load_kube_config(CUSTOMER_KUBECONFIG)
    return client.BatchV1Api(), client.CoreV1Api()

# create one shared Redis connection pool per process
redis_client: redis.Redis | None = None

@app.on_event("startup")
async def on_startup():
    await init_db()
    await init_kafka()

    global redis_client
    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

@app.on_event("shutdown")
async def on_shutdown():
    global redis_client
    if redis_client:
        await redis_client.aclose()
        redis_client = None


@app.post("/jobs/train")
async def submit_training_job(req: TrainJobRequest):
    job_id = str(uuid.uuid4())
    job_name = f"train-{job_id[:8]}"
    config_map_name = f"{job_name}-config"

    job_cfg = {
        "job_id": job_id,
        "model_id": req.model_id,
        "dataset_id": req.dataset_id,
        "epochs": req.epochs,
        "batch_size": req.batch_size,
        "lr": req.lr,
        "distributed": req.distributed,
        "extra": req.extra_config or {},
        "submitted_at": int(time.time()),
        "seq_start": 2,
    }

    try:
        await persist_initial_job(job_id, job_cfg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    event = JobEventIn(
        event_type=EventType.JOB_SUBMITTED,
        job_id=job_id,
        seq=1,
        producer="control-plane",
        payload={"config": job_cfg},
    )

    try:
        await send_event(event)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kafka error: {e}")

    return {"job_id": job_id, "status": "SUBMITTED"}


@app.get("/jobs", response_model=List[JobSummary])
async def list_jobs(limit: int = 100):
    rows = await fetch_jobs(limit=limit)
    summaries: List[JobSummary] = []

    for r in rows:
        summaries.append(
            JobSummary(
                job_id=r["job_id"],
                status=(r["status"] or "SUBMITTED"),  # should never be null now
                created_at=r["created_at"],
                submitted_at=r.get("submitted_at"),
                updated_at=r.get("updated_at"),
                config=json.loads(r["config"]) if isinstance(r["config"], str) else (r["config"] or {}),
            )
        )
    return summaries



@app.get("/jobs/{job_id}", response_model=JobSummary)
async def get_job(job_id: str) -> JobSummary:
    row = await fetch_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    cfg = row["config"]
    cfg_obj = json.loads(cfg) if isinstance(cfg, str) else (cfg or {})
    return JobSummary(
        job_id=row["job_id"],
        status=(row["status"] or "SUBMITTED"),
        created_at=row["created_at"],
        submitted_at=row.get("submitted_at"),
        updated_at=row.get("updated_at"),
        config=cfg_obj,
        model_id=cfg_obj.get("model_id"),
        dataset_id=cfg_obj.get("dataset_id"),
    )


@app.websocket("/ws/jobs/{job_id}")
async def ws_job_stream(websocket: WebSocket, job_id: str):
    await websocket.accept()

    # Each WS gets its own pubsub subscription
    if redis_client is None:
        await websocket.close(code=1011)
        return

    r = redis_client  # type: ignore
    pubsub = r.pubsub()
    channel = f"job_events:{job_id}"
    await pubsub.subscribe(channel)

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            raw = message["data"]
            try:
                event = json.loads(raw)
            except Exception:
                # If some old publisher sent non-JSON data
                continue

            try:
                event_out = JobEventOut.model_validate(event)
            except ValidationError:
                continue

            await websocket.send_json(event_out.model_dump())

    except WebSocketDisconnect:
        # client disconnected
        pass
    except Exception as e:
        print(f"ws_job_stream error for {job_id}: {e}", flush=True)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        try:
            await pubsub.unsubscribe(channel)
        except Exception:
            pass
        try:
            await pubsub.close()
        except Exception:
            pass


@app.get("/jobs/{job_id}/events")
async def get_job_events(job_id: str, since_id: int = 0, limit: int = 5000):
    prior_state: EventJobState | None = None
    if since_id > 0:
        prior_types = await fetch_job_event_types_until(job_id=job_id, up_to_id=since_id)
        for event_type in prior_types:
            prior_state = apply_event(prior_state, event_type)

    rows = await fetch_job_events_since(job_id=job_id, last_id=since_id, limit=limit)
    out = []
    state = prior_state
    for r in rows:
        data = r["payload"]
        if isinstance(data, str):
            data = json.loads(data)

        event_type = r["event_type"]
        state = apply_event(state, event_type)
        event_time = r["event_time"]
        event_time_iso = event_time.isoformat() if event_time else ""
        ts_ms = int(event_time.timestamp() * 1000) if event_time else 0

        out.append(
            JobEventOut(
                id=int(r["id"]),
                job_id=r["job_id"],
                event_time=event_time_iso or "",
                event_type=event_type,
                seq=int(r["seq"] or 0),
                ts_ms=ts_ms,
                producer=r["producer"] or "unknown",
                schema_version=int(r["schema_version"] or 1),
                data=data or {},
                state=state.value,
            ).model_dump()
        )
    return out
