"""Launch Kubernetes training jobs in response to Kafka events."""

import logging
import os
import socket
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


import os, asyncio, json, time, logging
import httpx
from aiokafka import AIOKafkaConsumer
from kubernetes import client
from kubernetes import config as k8s_config
from kubernetes.config.config_exception import ConfigException
from common.ai_training_common.kafka import build_kafka_config
from common.ai_training_common.events import JobEventIn, EventType


KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "job-events")
TRAINING_IMAGE = os.environ.get("TRAINING_IMAGE", "ai-platform-training-job:latest")
TRAINING_NAMESPACE = os.environ.get("TRAINING_NAMESPACE", "training-jobs")
CONTROL_PLANE_URL = os.environ.get("CONTROL_PLANE_URL", "")
DATA_PLANE_API_TOKEN = os.environ.get("DATA_PLANE_API_TOKEN", "")
DATA_PLANE_TENANT_ID = os.environ.get("DATA_PLANE_TENANT_ID", "")
DATA_PLANE_AGENT_ID = os.environ.get("DATA_PLANE_AGENT_ID") or os.environ.get("HOSTNAME") or socket.gethostname()

http_client: httpx.AsyncClient | None = None
cancelled_seen: set[str] = set()

async def process_job_submitted(job_id, cfg):
    """Create a Kubernetes Job and ConfigMap for a submitted job."""
    job_name = f"train-{job_id[:8]}"
    cm_name = f"{job_name}-config"
    v1 = client.CoreV1Api()
    try:
        v1.create_namespaced_config_map(
            namespace=TRAINING_NAMESPACE,
            body=client.V1ConfigMap(
                metadata=client.V1ObjectMeta(name=cm_name),
                data={"config.json": json.dumps(cfg)},
            ),
        )
    except Exception as e:
        print("ConfigMap create error:", e, flush=True)

    env_vars = [
        client.V1EnvVar(name="KAFKA_BOOTSTRAP", value=KAFKA_BOOTSTRAP),
        client.V1EnvVar(name="KAFKA_TOPIC", value=KAFKA_TOPIC),
        client.V1EnvVar(name="JOB_CONFIG", value="/opt/job/config.json"),
        client.V1EnvVar(name="JOB_ID", value=job_id),
    ]
    if _use_http_source():
        env_vars.append(client.V1EnvVar(name="CONTROL_PLANE_URL", value=CONTROL_PLANE_URL))
        if DATA_PLANE_API_TOKEN:
            env_vars.append(client.V1EnvVar(name="DATA_PLANE_API_TOKEN", value=DATA_PLANE_API_TOKEN))
        if DATA_PLANE_TENANT_ID:
            env_vars.append(client.V1EnvVar(name="DATA_PLANE_TENANT_ID", value=DATA_PLANE_TENANT_ID))

    container = client.V1Container(
        name="trainer",
        image=TRAINING_IMAGE,
        image_pull_policy="Never",
        volume_mounts=[client.V1VolumeMount(name="job-config", mount_path="/opt/job")],
        env=env_vars,
    )

    volume = client.V1Volume(
        name="job-config",
        config_map=client.V1ConfigMapVolumeSource(name=cm_name),
    )
    pod_spec = client.V1PodSpec(
        restart_policy="Never",
        containers=[container],
        volumes=[volume],
    )
    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels={"job-id": job_id}),
        spec=pod_spec,
    )
    job_spec = client.V1JobSpec(template=template, backoff_limit=3)
    job = client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(name=job_name),
        spec=job_spec,
    )
    batch = client.BatchV1Api()
    try:
        batch.create_namespaced_job(namespace=TRAINING_NAMESPACE, body=job)
        logger.info("Created training job %s (job_id=%s)", job_name, job_id)
    except Exception as e:
        print("Job create error:", e, flush=True)


async def process_job_cancelled(ev):
    """Delete the Kubernetes Job and ConfigMap for a cancelled job event."""
    job_id = ev["job_id"]
    job_name = f"train-{job_id[:8]}"
    cm_name = f"{job_name}-config"
    batch = client.BatchV1Api()
    core = client.CoreV1Api()
    try:
        batch.delete_namespaced_job(
            name=job_name,
            namespace=TRAINING_NAMESPACE,
            propagation_policy="Foreground",
        )
        print(f"Deleted job {job_name}", flush=True)
    except Exception as e:
        print("Job delete error:", e, flush=True)
    try:
        core.delete_namespaced_config_map(
            name=cm_name,
            namespace=TRAINING_NAMESPACE,
        )
        print(f"Deleted configmap {cm_name}", flush=True)
    except Exception as e:
        print("ConfigMap delete error:", e, flush=True)


def _use_http_source() -> bool:
    return bool(CONTROL_PLANE_URL)


def _data_plane_headers() -> dict:
    headers = {}
    if DATA_PLANE_API_TOKEN:
        headers["Authorization"] = f"Bearer {DATA_PLANE_API_TOKEN}"
    if DATA_PLANE_TENANT_ID:
        headers["X-Tenant-Id"] = DATA_PLANE_TENANT_ID
    if DATA_PLANE_AGENT_ID:
        headers["X-Agent-Id"] = DATA_PLANE_AGENT_ID
    return headers


async def init_http_client():
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(base_url=CONTROL_PLANE_URL.rstrip("/"))


async def close_http_client():
    global http_client
    if http_client:
        await http_client.aclose()
        http_client = None


async def fetch_pending_jobs(limit: int = 1, status_filter: str = "SUBMITTED"):
    if http_client is None:
        raise RuntimeError("HTTP client not initialized")
    resp = await http_client.get(
        "/internal/jobs",
        params={"status_filter": status_filter, "limit": limit},
        headers=_data_plane_headers(),
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json() or []


async def emit_job_pending(job_id: str, tenant_id: str, user_id: str):
    if http_client is None:
        raise RuntimeError("HTTP client not initialized")
    payload = JobEventIn.make(
        event_type=EventType.JOB_PENDING,
        job_id=job_id,
        tenant_id=tenant_id,
        user_id=user_id,
        seq=int(time.time()),
        producer="job-launcher",
        payload={},
    ).model_dump()
    resp = await http_client.post(
        "/internal/events",
        json=payload,
        headers=_data_plane_headers(),
        timeout=10.0,
    )
    resp.raise_for_status()


async def poll_forever():
    while True:
        try:
            jobs = await fetch_pending_jobs(limit=1)
            if not jobs:
                await asyncio.sleep(2)
            else:
                for job in jobs:
                    cfg = job.get("config") or {}
                    job_id = job.get("job_id")
                    if not job_id:
                        continue
                    tenant_id = cfg.get("tenant_id") or DATA_PLANE_TENANT_ID
                    user_id = cfg.get("user_id") or "data-plane"
                    if not tenant_id:
                        logger.warning("Skipping job %s without tenant_id", job_id)
                        continue
                    logger.info("Claiming submitted job %s (tenant_id=%s)", job_id, tenant_id)
                    await emit_job_pending(job_id, tenant_id, user_id)
                    logger.info("Emitted JOB_PENDING for %s", job_id)
                    await process_job_submitted(job_id, cfg)

            cancelled = await fetch_pending_jobs(limit=5, status_filter="CANCELLED")
            for job in cancelled:
                job_id = job.get("job_id")
                if job_id and job_id not in cancelled_seen:
                    await process_job_cancelled({"job_id": job_id})
                    cancelled_seen.add(job_id)
        except Exception:
            logger.exception("Polling failed; retrying in 3s")
            await asyncio.sleep(3)


async def run_http_mode():
    await init_http_client()
    try:
        await poll_forever()
    finally:
        await close_http_client()


async def consume_forever():
    """Continuously consume Kafka events with retry on failure."""
    while True:
        try:
            await consume_once()
        except Exception:
            logger.exception("Kafka consumer crashed; retrying in 3s")
            await asyncio.sleep(3)

async def consume_once():
    """Consume Kafka events until the consumer stops."""
    kafka_config = build_kafka_config()
    consumer = AIOKafkaConsumer(
        KAFKA_TOPIC,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        group_id="job-launcher",
        auto_offset_reset="earliest",
        **kafka_config,
    )
    await consumer.start()
    logger.info("Job launcher consumer started")
    try:
        async for msg in consumer:
            ev = msg.value
            if ev.get("event_type") == "JOB_SUBMITTED":
                job_id = ev.get("job_id")
                cfg = (ev.get("payload") or {}).get("config") or ev.get("config")
                if job_id and cfg:
                    await process_job_submitted(job_id, cfg)
            elif ev.get("event_type") == "JOB_CANCELLED":
                await process_job_cancelled(ev)
    finally:
        await consumer.stop()


def main():
    """Load Kubernetes config and start the Kafka consumer loop."""
    logger.info("Job Launcher starting... pid=%s", os.getpid())

    in_cluster = bool(os.getenv("KUBERNETES_SERVICE_HOST"))
    if in_cluster:
        logger.info("Running inside Kubernetes: loading in-cluster config")
        try:
            k8s_config.load_incluster_config()
        except Exception:
            # FULL traceback is critical here
            logger.exception("FATAL: failed to load in-cluster config")
            raise  # crash so you fix the real issue
        no_k8s = False
    else:
        logger.info("Local mode: loading kubeconfig")
        try:
            k8s_config.load_kube_config()
            no_k8s = False
        except ConfigException:
            logger.warning("No kubeconfig. Running with NO Kubernetes API.")
            no_k8s = True

    logger.info("Job launcher started. Kubernetes enabled = %s", not no_k8s)
    if _use_http_source():
        asyncio.run(run_http_mode())
    else:
        asyncio.run(consume_forever())

if __name__ == "__main__":
    main()
