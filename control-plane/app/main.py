from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from kubernetes import client, config as k8s_config
import uuid, time, json

from .config import (
    TRAINING_NAMESPACE,
    TRAINING_IMAGE,
    CUSTOMER_KUBECONFIG,
)
from .kafka_bus import init_kafka, send_event
from .db import init_db, persist_initial_job

app = FastAPI(title="AI Platform Control Plane")

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

    """
    try:
        batch_api, core_api = load_k8s_clients()
        cm = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(name=config_map_name),
            data={"config.json": json.dumps(job_cfg)},
        )
        core_api.create_namespaced_config_map(namespace=TRAINING_NAMESPACE, body=cm)
        container = client.V1Container(
            name="trainer",
            image=TRAINING_IMAGE,
            volume_mounts=[
                client.V1VolumeMount(name="job-config", mount_path="/opt/job")
            ],
        )
        volume = client.V1Volume(
            name="job-config",
            config_map=client.V1ConfigMapVolumeSource(name=config_map_name),
        )
        pod_spec = client.V1PodSpec(
            restart_policy="Never", containers=[container], volumes=[volume]
        )
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels={"job-id": job_id}), spec=pod_spec
        )
        job_spec = client.V1JobSpec(template=template, backoff_limit=3)
        job = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(name=job_name),
            spec=job_spec,
        )
        batch_api.create_namespaced_job(namespace=TRAINING_NAMESPACE, body=job)
    except Exception as e:
        print("K8s direct job submit failed:", e, flush=True)
    """
    return {"job_id": job_id, "status": "SUBMITTED"}
