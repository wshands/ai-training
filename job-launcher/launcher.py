import os, asyncio, json
from aiokafka import AIOKafkaConsumer
from kubernetes import client, config

from kubernetes.config.config_exception import ConfigException


KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "job-events")
TRAINING_IMAGE = os.environ.get("TRAINING_IMAGE", "ai-platform-training-job:latest")
TRAINING_NAMESPACE = os.environ.get("TRAINING_NAMESPACE", "training-jobs")

async def process_job_submitted(ev):
    job_id = ev["job_id"]
    cfg = ev["config"]
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

async def consume():
    consumer = AIOKafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP.split(","),
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        group_id="job-launcher",
        auto_offset_reset="earliest",
    )
    await consumer.start()
    print("Job launcher consumer started", flush=True)
    try:
        async for msg in consumer:
            ev = msg.value
            if ev.get("type") == "JOB_SUBMITTED":
                await process_job_submitted(ev)
    finally:
        await consumer.stop()

def main():
    print("Job Launcher starting...")

    # Are we running inside Kubernetes?
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        print("Running inside Kubernetes: loading in-cluster config")
        try:
            config.load_incluster_config()
            return run_job_launcher(no_k8s=False)
        except Exception as e:
            print("Failed to load in-cluster config:", e)

    # Otherwise, assume local dev mode
    try:
        print("Loading local kubeconfig...")
        config.load_kube_config()
        return run_job_launcher(no_k8s=False)
    except ConfigException:
        print("No kubeconfig. Running with NO Kubernetes API.")
        return run_job_launcher(no_k8s=True)


def run_job_launcher(no_k8s=False):
    print("Job launcher started. Kubernetes enabled =", not no_k8s)
    asyncio.run(consume())




"""
def main():
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        config.load_incluster_config()
    else:
        config.load_kube_config()
    asyncio.run(consume())
"""
if __name__ == "__main__":
    main()
