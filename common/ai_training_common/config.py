"""Environment-driven configuration defaults."""

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
DEFAULT_TENANT_ID = os.environ.get("DEFAULT_TENANT_ID", "local-dev-tenant")
DEFAULT_USER_ID = os.environ.get("DEFAULT_USER_ID", "local-dev-user")
CLERK_JWKS_URL = os.environ.get("CLERK_JWKS_URL", "")
CLERK_ISSUER = os.environ.get("CLERK_ISSUER", "")
CLERK_AUDIENCE = os.environ.get("CLERK_AUDIENCE", "")
CLERK_JWT_ALGORITHM = os.environ.get("CLERK_JWT_ALGORITHM", "RS256")
