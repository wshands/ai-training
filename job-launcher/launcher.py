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


import os, asyncio, json, time, logging
from aiokafka import AIOKafkaConsumer
from kubernetes import client
from kubernetes import config as k8s_config
from kubernetes.config.config_exception import ConfigException


KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "job-events")
TRAINING_IMAGE = os.environ.get("TRAINING_IMAGE", "ai-platform-training-job:latest")
TRAINING_NAMESPACE = os.environ.get("TRAINING_NAMESPACE", "training-jobs")

async def process_job_submitted(ev):
    job_id = ev["job_id"]
    cfg = (ev.get("payload") or {}).get("config") or ev.get("config")
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

    container = client.V1Container(
        name="trainer",
        image=TRAINING_IMAGE,
        image_pull_policy="Never",
        volume_mounts=[client.V1VolumeMount(name="job-config", mount_path="/opt/job")],
        env=[
            client.V1EnvVar(name="KAFKA_BOOTSTRAP", value=KAFKA_BOOTSTRAP),
            client.V1EnvVar(name="KAFKA_TOPIC", value=KAFKA_TOPIC),
            client.V1EnvVar(name="JOB_CONFIG", value="/opt/job/config.json"),
            client.V1EnvVar(name="JOB_ID", value=job_id),
        ],
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
        print(f"Created job {job_name}", flush=True)
    except Exception as e:
        print("Job create error:", e, flush=True)


async def process_job_cancelled(ev):
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


async def consume_forever():
    while True:
        try:
            await consume_once()
        except Exception:
            logger.exception("Kafka consumer crashed; retrying in 3s")
            await asyncio.sleep(3)

async def consume_once():
    consumer = AIOKafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP.split(","),
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        group_id="job-launcher",
        auto_offset_reset="earliest",
    )
    await consumer.start()
    logger.info("Job launcher consumer started")
    try:
        async for msg in consumer:
            ev = msg.value
            if ev.get("event_type") == "JOB_SUBMITTED":
                await process_job_submitted(ev)
            elif ev.get("event_type") == "JOB_CANCELLED":
                await process_job_cancelled(ev)
    finally:
        await consumer.stop()


def main():
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
    asyncio.run(consume_forever())

if __name__ == "__main__":
    main()
