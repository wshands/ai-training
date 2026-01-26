
"""Control-plane API for job submission, status, and event streaming."""

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
    """Configure process-wide logging with an env-driven log level."""
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
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from kubernetes import client, config as k8s_config
from pydantic import BaseModel, Field, ValidationError
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager
import jwt
from jwt import PyJWKClientError

#from fastapi import WebSocket
from common.ai_training_common.config import (
    TRAINING_NAMESPACE,
    TRAINING_IMAGE,
    CUSTOMER_KUBECONFIG,
    REDIS_URL,
    CLERK_JWKS_URL,
    CLERK_ISSUER,
    CLERK_AUDIENCE,
    CLERK_JWT_ALGORITHM,
)
from .kafka_bus import init_kafka, send_event
from common.ai_training_common.db import (
    init_db,
    persist_initial_job,
    fetch_jobs,
    fetch_job_events_since,
    fetch_job_events_before,
    fetch_job_events_latest,
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
    last_error: Optional[Dict[str, Any]] = None


class AuthContext(BaseModel):
    user_id: str
    tenant_id: str
    email: Optional[str] = None
    role: Optional[str] = None

DEFAULT_JOBS_LIMIT = 50
MAX_JOBS_LIMIT = 200
DEFAULT_EVENTS_LIMIT = 500
MAX_EVENTS_LIMIT = 2000

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize shared resources and clean them up on shutdown."""
    await init_db()
    await init_kafka()
    global redis_client
    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        yield
    finally:
        if redis_client:
            await redis_client.aclose()
            redis_client = None


app = FastAPI(title="AI Platform Control Plane", lifespan=lifespan)

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

bearer_scheme = HTTPBearer(auto_error=False)
_jwks_client: jwt.PyJWKClient | None = None


def get_jwks_client() -> jwt.PyJWKClient:
    """Return a cached JWKS client for Clerk token verification."""
    global _jwks_client
    if _jwks_client is None:
        if not CLERK_JWKS_URL:
            raise HTTPException(status_code=500, detail="CLERK_JWKS_URL is not configured")
        _jwks_client = jwt.PyJWKClient(CLERK_JWKS_URL)
    return _jwks_client


def decode_clerk_token(token: str) -> AuthContext:
    """Validate a Clerk JWT and return the derived auth context."""
    try:
        jwk_client = get_jwks_client()
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        options = {"verify_aud": bool(CLERK_AUDIENCE)}
        decode_kwargs = {
            "key": signing_key.key,
            "algorithms": [CLERK_JWT_ALGORITHM],
            "options": options,
        }
        if CLERK_AUDIENCE:
            decode_kwargs["audience"] = CLERK_AUDIENCE
        if CLERK_ISSUER:
            decode_kwargs["issuer"] = CLERK_ISSUER
        payload = jwt.decode(token, **decode_kwargs)
    except PyJWKClientError as e:
        logger.error("JWKS fetch/parse error: %s", e)
        raise HTTPException(status_code=503, detail="Auth key retrieval failed")
    except jwt.PyJWTError as e:
        logger.warning("JWT verification failed: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except Exception as e:
        logger.error("Token verification error: %s", e)
        raise HTTPException(status_code=500, detail="Token verification error")

    user_id = payload.get("sub")
    tenant_id = payload.get("org_id") or payload.get("orgId") or user_id
    if not user_id or not tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        email=payload.get("email") or payload.get("email_address"),
        role=payload.get("org_role"),
    )


def get_current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthContext:
    """FastAPI dependency to validate bearer tokens for HTTP requests."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return decode_clerk_token(credentials.credentials)


def get_ws_identity(websocket: WebSocket) -> AuthContext:
    """Validate a token for WebSocket connections via query param or header."""
    token = websocket.query_params.get("token")
    if not token:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1]
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    return decode_clerk_token(token)


class TrainJobRequest(BaseModel):
    model_id: str
    dataset_id: str
    epochs: int = 1
    batch_size: int = 32
    lr: float = 1e-3
    distributed: bool = False
    extra_config: dict | None = None


def load_k8s_clients():
    """Load kubeconfig and return Kubernetes API clients."""
    k8s_config.load_kube_config(CUSTOMER_KUBECONFIG)
    return client.BatchV1Api(), client.CoreV1Api()

# create one shared Redis connection pool per process
redis_client: redis.Redis | None = None



@app.get("/auth/me", response_model=AuthContext)
async def me(identity: AuthContext = Depends(get_current_identity)):
    """Return the caller's auth context for debugging."""
    return identity


@app.post("/jobs/train")
async def submit_training_job(
    req: TrainJobRequest,
    identity: AuthContext = Depends(get_current_identity),
):
    """Create a new job record and emit a submission event."""
    tenant_id, user_id = identity.tenant_id, identity.user_id
    job_id = str(uuid.uuid4())
    job_name = f"train-{job_id[:8]}"
    config_map_name = f"{job_name}-config"

    job_cfg = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "model_id": req.model_id,
        "dataset_id": req.dataset_id,
        "epochs": req.epochs,
        "batch_size": req.batch_size,
        "lr": req.lr,
        "distributed": req.distributed,
        "extra": req.extra_config or {},
        "submitted_at": int(time.time()),
        "seq_start": 2,

        #"fail_after_epoch": 5,  # for testing only!!!! remove in prod
    }

    try:
        await persist_initial_job(job_id, job_cfg, tenant_id, user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    event = JobEventIn(
        event_type=EventType.JOB_SUBMITTED,
        job_id=job_id,
        tenant_id=tenant_id,
        user_id=user_id,
        seq=1,
        producer="control-plane",
        payload={"config": job_cfg},
    )

    try:
        await send_event(event)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kafka error: {e}")

    return {"job_id": job_id, "status": "SUBMITTED"}


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    identity: AuthContext = Depends(get_current_identity),
):
    """Emit a cancellation event for a job."""
    tenant_id, user_id = identity.tenant_id, identity.user_id
    row = await fetch_job(tenant_id, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    event = JobEventIn(
        event_type=EventType.JOB_CANCELLED,
        job_id=job_id,
        tenant_id=tenant_id,
        user_id=user_id,
        seq=int(time.time()),
        producer="control-plane",
        payload={"reason": "cancelled_by_user"},
    )

    try:
        await send_event(event)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kafka error: {e}")

    return {"job_id": job_id, "status": "CANCELLED"}


@app.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: str,
    identity: AuthContext = Depends(get_current_identity),
):
    """Create a new job based on a previous job's config."""
    tenant_id, user_id = identity.tenant_id, identity.user_id
    row = await fetch_job(tenant_id, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    cfg = row["config"]
    cfg_obj = json.loads(cfg) if isinstance(cfg, str) else (cfg or {})

    new_job_id = str(uuid.uuid4())
    job_cfg = dict(cfg_obj)
    job_cfg.update(
        {
            "job_id": new_job_id,
            "submitted_at": int(time.time()),
            "seq_start": 2,
            "retry_of": job_id,
        }
    )

    try:
        await persist_initial_job(new_job_id, job_cfg, tenant_id, user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    event = JobEventIn(
        event_type=EventType.JOB_SUBMITTED,
        job_id=new_job_id,
        tenant_id=tenant_id,
        user_id=user_id,
        seq=1,
        producer="control-plane",
        payload={"config": job_cfg},
    )

    try:
        await send_event(event)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kafka error: {e}")

    return {"job_id": new_job_id, "status": "SUBMITTED"}


@app.get("/jobs", response_model=List[JobSummary])
async def list_jobs(
    limit: int = DEFAULT_JOBS_LIMIT,
    offset: int = 0,
    identity: AuthContext = Depends(get_current_identity),
):
    """List job summaries for the caller's tenant."""
    tenant_id = identity.tenant_id
    safe_limit = max(1, min(limit, MAX_JOBS_LIMIT))
    safe_offset = max(0, offset)
    rows = await fetch_jobs(tenant_id, limit=safe_limit, offset=safe_offset)
    summaries: List[JobSummary] = []

    for r in rows:
        last_event = r.get("last_event")
        if isinstance(last_event, str):
            last_event = json.loads(last_event)
        last_error = (last_event or {}).get("error")
        summaries.append(
            JobSummary(
                job_id=r["job_id"],
                status=(r["status"] or "SUBMITTED"),  # should never be null now
                created_at=r["created_at"],
                submitted_at=r.get("submitted_at"),
                updated_at=r.get("updated_at"),
                config=json.loads(r["config"]) if isinstance(r["config"], str) else (r["config"] or {}),
                last_error=last_error,
            )
        )
    return summaries



@app.get("/jobs/{job_id}", response_model=JobSummary)
async def get_job(
    job_id: str,
    identity: AuthContext = Depends(get_current_identity),
) -> JobSummary:
    """Return a single job summary for the tenant."""
    tenant_id = identity.tenant_id
    row = await fetch_job(tenant_id, job_id)
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
    """Stream job events for a single job over WebSocket."""
    await websocket.accept()
    try:
        identity = get_ws_identity(websocket)
    except HTTPException:
        await websocket.close(code=1008)
        return

    row = await fetch_job(identity.tenant_id, job_id)
    if not row:
        await websocket.close(code=1008)
        return

    # Each WS gets its own pubsub subscription
    if redis_client is None:
        await websocket.close(code=1011)
        return

    r = redis_client  # type: ignore
    pubsub = r.pubsub()
    channel = f"job_events:{identity.tenant_id}"
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
            if event_out.tenant_id != identity.tenant_id:
                continue
            if event_out.job_id != job_id:
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


@app.websocket("/ws/jobs")
async def ws_jobs_stream(websocket: WebSocket):
    """Stream job events for a tenant over WebSocket."""
    await websocket.accept()
    try:
        identity = get_ws_identity(websocket)
    except HTTPException:
        await websocket.close(code=1008)
        return

    if redis_client is None:
        await websocket.close(code=1011)
        return

    r = redis_client  # type: ignore
    pubsub = r.pubsub()
    channel = f"job_events:{identity.tenant_id}"
    await pubsub.subscribe(channel)

    try:
        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue

            raw = message["data"]
            try:
                event = json.loads(raw)
            except Exception:
                continue

            try:
                event_out = JobEventOut.model_validate(event)
            except ValidationError:
                continue
            if event_out.tenant_id != identity.tenant_id:
                continue

            await websocket.send_json(event_out.model_dump())

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"ws_jobs_stream error: {e}", flush=True)
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


def _render_job_events(
    rows: List[Dict[str, Any]],
    *,
    include_state: bool,
    prior_state: EventJobState | None,
) -> List[Dict[str, Any]]:
    """Convert event rows to API output, optionally computing state."""
    out = []
    state = prior_state
    for r in rows:
        data = r["payload"]
        if isinstance(data, str):
            data = json.loads(data)

        event_type = r["event_type"]
        if include_state:
            state = apply_event(state, event_type)
            state_value = state.value
        else:
            state_value = ""

        event_time = r["event_time"]
        event_time_iso = event_time.isoformat() if event_time else ""
        ts_ms = int(event_time.timestamp() * 1000) if event_time else 0

        out.append(
            JobEventOut(
                id=int(r["id"]),
                job_id=r["job_id"],
                tenant_id=r["tenant_id"],
                user_id=r["user_id"],
                event_time=event_time_iso or "",
                event_type=event_type,
                seq=int(r["seq"] or 0),
                ts_ms=ts_ms,
                producer=r["producer"] or "unknown",
                schema_version=int(r["schema_version"] or 1),
                data=data or {},
                state=state_value,
            ).model_dump()
        )
    return out


@app.get("/jobs/{job_id}/events")
async def get_job_events(
    job_id: str,
    since_id: int = 0,
    before_id: int | None = None,
    limit: int = DEFAULT_EVENTS_LIMIT,
    include_state: bool = True,
    identity: AuthContext = Depends(get_current_identity),
):
    """Return paginated job events, with optional state replay."""
    tenant_id = identity.tenant_id
    safe_limit = max(1, min(limit, MAX_EVENTS_LIMIT))

    prior_state: EventJobState | None = None
    if include_state:
        if before_id is not None and before_id > 0:
            prior_types = await fetch_job_event_types_until(
                tenant_id=tenant_id,
                job_id=job_id,
                up_to_id=before_id - 1,
            )
            for event_type in prior_types:
                prior_state = apply_event(prior_state, event_type)
        elif since_id > 0:
            prior_types = await fetch_job_event_types_until(
                tenant_id=tenant_id,
                job_id=job_id,
                up_to_id=since_id,
            )
            for event_type in prior_types:
                prior_state = apply_event(prior_state, event_type)

    if before_id is not None:
        rows = await fetch_job_events_before(
            tenant_id=tenant_id,
            job_id=job_id,
            before_id=before_id,
            limit=safe_limit,
        )
        rows = sorted(rows, key=lambda r: int(r["id"]))
    else:
        rows = await fetch_job_events_since(
            tenant_id=tenant_id,
            job_id=job_id,
            last_id=since_id,
            limit=safe_limit,
        )
    return _render_job_events(rows, include_state=include_state, prior_state=prior_state)


@app.get("/jobs/{job_id}/events/latest")
async def get_latest_job_events(
    job_id: str,
    limit: int = DEFAULT_EVENTS_LIMIT,
    include_state: bool = False,
    identity: AuthContext = Depends(get_current_identity),
):
    """Return the latest events for a job without history replay by default."""
    tenant_id = identity.tenant_id
    safe_limit = max(1, min(limit, MAX_EVENTS_LIMIT))
    rows = await fetch_job_events_latest(
        tenant_id=tenant_id,
        job_id=job_id,
        limit=safe_limit,
    )
    rows = sorted(rows, key=lambda r: int(r["id"]))

    prior_state: EventJobState | None = None
    if include_state and rows:
        oldest_id = int(rows[0]["id"])
        if oldest_id > 1:
            prior_types = await fetch_job_event_types_until(
                tenant_id=tenant_id,
                job_id=job_id,
                up_to_id=oldest_id - 1,
            )
            for event_type in prior_types:
                prior_state = apply_event(prior_state, event_type)

    return _render_job_events(rows, include_state=include_state, prior_state=prior_state)
