import os

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "job-events")
POSTGRES_DSN = os.environ.get("POSTGRES_DSN", "postgresql://postgres:postgres@postgres:5432/controlplane")
TRAINING_NAMESPACE = os.environ.get("TRAINING_NAMESPACE", "training-jobs")
TRAINING_IMAGE = os.environ.get("TRAINING_IMAGE", "ai-platform/training-job:latest")
CUSTOMER_KUBECONFIG = os.environ.get("CUSTOMER_KUBECONFIG", "/app/kubeconfig.yaml")
API_HOST = os.environ.get("API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("API_PORT", "8000"))
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")  # or wherever your Redis lives
