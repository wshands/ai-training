
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
    if os.getenv("SUPPRESS_INTERNAL_ACCESS_LOGS", "true").lower() in ("1", "true", "yes"):
        logging.getLogger("uvicorn.access").addFilter(_InternalAccessLogFilter())


class _InternalAccessLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return "/internal/jobs" not in message

setup_logging()
logger = logging.getLogger(__name__)

import uuid
import time
import json
import secrets
import redis.asyncio as redis

from datetime import datetime
from enum import Enum
from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from kubernetes import client, config as k8s_config
from pydantic import BaseModel, Field, ValidationError, ConfigDict
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
    DATA_PLANE_API_TOKEN,
    DATA_PLANE_TENANT_ID,
    DATA_PLANE_API_TOKENS,
    DATA_PLANE_LOG_POLLS,
    parse_data_plane_tokens,
    CONTROL_PLANE_ADMIN_TOKEN,
)
from .kafka_bus import init_kafka, send_event
from common.ai_training_common.db import (
    init_db,
    persist_initial_job,
    fetch_jobs,
    fetch_jobs_by_state,
    fetch_job_events_since,
    fetch_job_events_before,
    fetch_job_events_latest,
    fetch_job,
)
from common.ai_training_common.events import JobEventIn, JobEventOut, EventType


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


class DataPlaneContext(BaseModel):
    tenant_id: str
    agent_id: str


DATA_PLANE_TOKENS: dict[str, list[str]] = parse_data_plane_tokens(DATA_PLANE_API_TOKENS)
DATA_PLANE_TOKEN_REDIS_KEY = "data_plane_tokens"


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


def _extract_bearer_token(request: Request) -> str | None:
    token = request.headers.get("x-data-plane-token")
    if token:
        return token
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1]
    return None


def get_admin_identity(request: Request) -> None:
    """Validate the admin token for internal admin endpoints."""
    if not CONTROL_PLANE_ADMIN_TOKEN:
        raise HTTPException(status_code=500, detail="CONTROL_PLANE_ADMIN_TOKEN not configured")
    token = _extract_bearer_token(request)
    if token != CONTROL_PLANE_ADMIN_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")


async def _load_data_plane_tokens() -> dict[str, list[str]]:
    if redis_client is None:
        return DATA_PLANE_TOKENS
    raw = await redis_client.get(DATA_PLANE_TOKEN_REDIS_KEY)
    if not raw:
        return DATA_PLANE_TOKENS
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return DATA_PLANE_TOKENS
    tokens_map: dict[str, list[str]] = {}
    for tenant_id, tokens in (data or {}).items():
        if isinstance(tokens, str):
            tokens_map[tenant_id] = [tokens]
        elif isinstance(tokens, list):
            tokens_map[tenant_id] = [t for t in tokens if isinstance(t, str)]
    return tokens_map


async def _store_data_plane_tokens(tokens_map: dict[str, list[str]]) -> None:
    global DATA_PLANE_TOKENS
    DATA_PLANE_TOKENS = tokens_map
    if redis_client is None:
        return
    await redis_client.set(DATA_PLANE_TOKEN_REDIS_KEY, json.dumps(tokens_map))


async def get_data_plane_identity(request: Request) -> DataPlaneContext:
    """Authenticate data-plane requests using a shared token."""
    if not DATA_PLANE_API_TOKEN and not DATA_PLANE_TOKENS:
        raise HTTPException(status_code=500, detail="DATA_PLANE_API_TOKEN not configured")

    token = _extract_bearer_token(request)

    tenant_id = request.headers.get("x-tenant-id") or DATA_PLANE_TENANT_ID
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing tenant id")
    if DATA_PLANE_TENANT_ID and tenant_id != DATA_PLANE_TENANT_ID:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")

    tokens_map = await _load_data_plane_tokens()
    if tokens_map:
        allowed_tokens = tokens_map.get(tenant_id, [])
        if token not in allowed_tokens:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid data-plane token")
    elif token != DATA_PLANE_API_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid data-plane token")

    agent_id = request.headers.get("x-agent-id") or "unknown"
    return DataPlaneContext(tenant_id=tenant_id, agent_id=agent_id)


class TrainJobRequest(BaseModel):
    model_id: str
    dataset_id: str
    epochs: int = 1
    batch_size: int = 32
    lr: float = 1e-3
    distributed: bool = False
    extra_config: dict | None = None


class JobConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    job_id: str
    tenant_id: str
    user_id: str
    model_id: str
    dataset_id: str
    epochs: int
    batch_size: int
    lr: float
    distributed: bool
    extra: dict = Field(default_factory=dict)
    submitted_at: int
    seq_start: int
    retry_of: Optional[str] = None


class DataPlaneTokenRequest(BaseModel):
    tenant_id: str
    token: Optional[str] = None


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

    job_cfg = JobConfig(
        job_id=job_id,
        tenant_id=tenant_id,
        user_id=user_id,
        model_id=req.model_id,
        dataset_id=req.dataset_id,
        epochs=req.epochs,
        batch_size=req.batch_size,
        lr=req.lr,
        distributed=req.distributed,
        extra=req.extra_config or {},
        submitted_at=int(time.time()),
        seq_start=2,
    )
    job_cfg_dict = job_cfg.model_dump()

    try:
        await persist_initial_job(job_id, job_cfg_dict, tenant_id, user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    event = JobEventIn(
        event_type=EventType.JOB_SUBMITTED,
        job_id=job_id,
        tenant_id=tenant_id,
        user_id=user_id,
        seq=1,
        producer="control-plane",
        payload={"config": job_cfg_dict},
    )

    try:
        await send_event(event)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kafka error: {e}")

    return {"job_id": job_id, "status": JobState.SUBMITTED.value}


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

    return {"job_id": job_id, "status": JobState.CANCELLED.value}


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
    job_cfg = JobConfig(
        **cfg_obj,
        job_id=new_job_id,
        submitted_at=int(time.time()),
        seq_start=2,
        retry_of=job_id,
    )
    job_cfg_dict = job_cfg.model_dump()

    try:
        await persist_initial_job(new_job_id, job_cfg_dict, tenant_id, user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    event = JobEventIn(
        event_type=EventType.JOB_SUBMITTED,
        job_id=new_job_id,
        tenant_id=tenant_id,
        user_id=user_id,
        seq=1,
        producer="control-plane",
        payload={"config": job_cfg_dict},
    )

    try:
        await send_event(event)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kafka error: {e}")

    return {"job_id": new_job_id, "status": JobState.SUBMITTED.value}


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
                status=(r["status"] or JobState.SUBMITTED.value),  # should never be null now
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
        status=(row["status"] or JobState.SUBMITTED.value),
        created_at=row["created_at"],
        submitted_at=row.get("submitted_at"),
        updated_at=row.get("updated_at"),
        config=cfg_obj,
        model_id=cfg_obj.get("model_id"),
        dataset_id=cfg_obj.get("dataset_id"),
    )


@app.get("/internal/jobs", response_model=List[JobSummary])
async def list_pending_jobs(
    status_filter: str = JobState.SUBMITTED.value,
    limit: int = DEFAULT_JOBS_LIMIT,
    identity: DataPlaneContext = Depends(get_data_plane_identity),
):
    """List jobs for the data plane by status."""
    safe_limit = max(1, min(limit, MAX_JOBS_LIMIT))
    if DATA_PLANE_LOG_POLLS:
        logger.info(
            "Data-plane poll agent_id=%s tenant_id=%s status=%s limit=%s",
            identity.agent_id,
            identity.tenant_id,
            status_filter,
            safe_limit,
        )
    rows = await fetch_jobs_by_state(identity.tenant_id, status_filter, safe_limit)
    summaries: List[JobSummary] = []
    for r in rows:
        last_event = r.get("last_event")
        if isinstance(last_event, str):
            last_event = json.loads(last_event)
        last_error = (last_event or {}).get("error")
        cfg = r["config"]
        cfg_obj = json.loads(cfg) if isinstance(cfg, str) else (cfg or {})
        summaries.append(
            JobSummary(
                job_id=r["job_id"],
                status=(r["status"] or JobState.SUBMITTED.value),
                created_at=r["created_at"],
                submitted_at=r.get("submitted_at"),
                updated_at=r.get("updated_at"),
                config=cfg_obj,
                last_error=last_error,
            )
        )
    return summaries


@app.post("/internal/events")
async def ingest_data_plane_event(
    event: JobEventIn,
    identity: DataPlaneContext = Depends(get_data_plane_identity),
):
    """Ingest a data-plane event and publish it to Kafka."""
    if event.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    try:
        await send_event(event)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kafka error: {e}")
    return {"status": "accepted", "event_id": event.event_id}


@app.get("/internal/admin/data-plane-tokens")
async def list_data_plane_tokens(
    tenant_id: Optional[str] = None,
    _: None = Depends(get_admin_identity),
):
    """List data-plane tokens for all tenants or a specific tenant."""
    tokens_map = await _load_data_plane_tokens()
    if tenant_id:
        return {tenant_id: tokens_map.get(tenant_id, [])}
    return tokens_map


@app.post("/internal/admin/data-plane-tokens")
async def mint_data_plane_token(
    req: DataPlaneTokenRequest,
    _: None = Depends(get_admin_identity),
):
    """Mint a data-plane token for a tenant (manual rotation)."""
    tokens_map = await _load_data_plane_tokens()
    token = req.token or secrets.token_urlsafe(32)
    tokens = list(tokens_map.get(req.tenant_id, []))
    if token not in tokens:
        tokens.append(token)
    tokens_map[req.tenant_id] = tokens
    await _store_data_plane_tokens(tokens_map)
    return {"tenant_id": req.tenant_id, "token": token, "tokens": tokens}


@app.delete("/internal/admin/data-plane-tokens")
async def revoke_data_plane_token(
    req: DataPlaneTokenRequest,
    _: None = Depends(get_admin_identity),
):
    """Remove a data-plane token or clear all tokens for a tenant."""
    tokens_map = await _load_data_plane_tokens()
    tokens = list(tokens_map.get(req.tenant_id, []))

    if req.token:
        tokens = [t for t in tokens if t != req.token]
    else:
        tokens = []

    if tokens:
        tokens_map[req.tenant_id] = tokens
    else:
        tokens_map.pop(req.tenant_id, None)

    await _store_data_plane_tokens(tokens_map)
    return {"tenant_id": req.tenant_id, "tokens": tokens}


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


def _render_job_events(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert event rows to API output without replaying state."""
    out = []
    for r in rows:
        data = r["payload"]
        if isinstance(data, str):
            data = json.loads(data)

        event_type = r["event_type"]
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
            ).model_dump(exclude={"state"})
        )
    return out


@app.get("/jobs/{job_id}/events")
async def get_job_events(
    job_id: str,
    since_id: int = 0,
    before_id: int | None = None,
    limit: int = DEFAULT_EVENTS_LIMIT,
    identity: AuthContext = Depends(get_current_identity),
):
    """Return paginated job events without replaying state."""
    tenant_id = identity.tenant_id
    safe_limit = max(1, min(limit, MAX_EVENTS_LIMIT))

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
    return _render_job_events(rows)


@app.get("/jobs/{job_id}/events/latest")
async def get_latest_job_events(
    job_id: str,
    limit: int = DEFAULT_EVENTS_LIMIT,
    identity: AuthContext = Depends(get_current_identity),
):
    """Return the latest events for a job without history replay."""
    tenant_id = identity.tenant_id
    safe_limit = max(1, min(limit, MAX_EVENTS_LIMIT))
    rows = await fetch_job_events_latest(
        tenant_id=tenant_id,
        job_id=job_id,
        limit=safe_limit,
    )
    rows = sorted(rows, key=lambda r: int(r["id"]))
    return _render_job_events(rows)
