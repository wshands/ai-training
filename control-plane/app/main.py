from enum import Enum

from fastapi import FastAPI, HTTPException

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocket, WebSocketDisconnect

from fastapi import WebSocket




import uuid, time, json, asyncio


from .config import (
    TRAINING_NAMESPACE,
    TRAINING_IMAGE,
    CUSTOMER_KUBECONFIG,
)
from .kafka_bus import init_kafka, send_event
from .db import (
    init_db,
    persist_initial_job,
    fetch_jobs,
    fetch_job,
    fetch_job_events_since,
)
# plus the models you defined above:
# JobState, TrainJobRequest, JobSummary, JobDetail, JobEvent, DeploymentSummary



from pydantic import BaseModel, Field

from typing import Any, Dict, List, Optional
from datetime import datetime

from kubernetes import client, config as k8s_config




class JobState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PREEMPTED = "PREEMPTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class JobSummary(BaseModel):
    job_id: str
    status: JobState = JobState.UNKNOWN
    created_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    config: Dict[str, Any] = Field(default_factory=dict)


class JobEvent(BaseModel):
    id: int
    job_id: str
    event_time: Optional[datetime] = None
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class JobDetail(JobSummary):
    events: List[JobEvent] = Field(default_factory=list)

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

@app.on_event("startup")
async def startup():
    await init_db()
    await init_kafka()

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
    }

    try:
        await persist_initial_job(job_id, job_cfg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    event = {
        "type": "JOB_SUBMITTED",
        "job_id": job_id,
        "timestamp": int(time.time()),
        "config": job_cfg,
    }
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
                status=(r["status"] or "UNKNOWN"),
                created_at=r["created_at"],
                submitted_at=r.get("submitted_at"),
                updated_at=r.get("updated_at"),
                config=r["config"] or {},
            )
        )
    return summaries



@app.websocket("/ws/jobs/{job_id}")
async def job_event_stream(websocket: WebSocket, job_id: str):
    await websocket.accept()
    last_id = 0
    try:
        while True:
            events = await fetch_job_events_since(job_id, last_id=last_id, limit=200)
            for e in events:
                last_id = e["id"]
                payload = e["payload"] or {}
                event_type = e["event_type"] or payload.get("event_type", "UNKNOWN")

                # Map raw events into frontend-friendly messages.
                #
                # You can shape this however you like, but one common mapping is:
                # - JOB_LOG        -> {type: "log", message: "..."}
                # - JOB_METRIC     -> {type: "metric", metric: {...}}
                # - JOB_* state    -> {type: "status", status: "RUNNING"/...}
                msg: dict[str, Any]

                if event_type == "JOB_LOG":
                    msg = {"type": "log", "message": payload.get("message", "")}
                elif event_type == "JOB_METRIC":
                    msg = {"type": "metric", "metric": payload.get("metric", {})}
                elif event_type.startswith("JOB_"):
                    # derive state using the same enum as event-processor.state_machine
                    msg = {"type": "status", "status": payload.get("state", event_type)}
                else:
                    msg = {
                        "type": "raw_event",
                        "event_type": event_type,
                        "payload": payload,
                    }

                await websocket.send_json(msg)

            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        # client closed
        return
    except Exception as e:
        # log and close
        print("Error in job_event_stream:", e, flush=True)
        await websocket.close(code=1011)
