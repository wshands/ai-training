#!/usr/bin/env bash
# Run from anywhere; the script resolves paths relative to its own location.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CP_TF_DIR="${ROOT_DIR}/deploy/terraform/control-plane"
SECRET_RESOURCE="aws_secretsmanager_secret.postgres_dsn"
SECRET_NAME="${POSTGRES_DSN_SECRET_NAME:-ai-platform/postgres-dsn}"
IMPORT_OUTPUT="/tmp/terraform-import-$$.log"

export AWS_SDK_LOAD_CONFIG=1
export AWS_PROFILE="${AWS_PROFILE:-AdministratorAccess-230407893272}"

if ! command -v terraform >/dev/null 2>&1; then
  echo "terraform is required. Install it first." >&2
  exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "aws CLI is required. Install it first." >&2
  exit 1
fi

if [[ ! -d "$CP_TF_DIR" ]]; then
  echo "Terraform control-plane directory not found: $CP_TF_DIR" >&2
  exit 1
fi

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "AWS credentials not available. If using SSO, run:" >&2
  echo "  aws sso login --profile ${AWS_PROFILE}" >&2
  exit 1
fi

echo "Initializing Terraform..."
terraform -chdir="$CP_TF_DIR" init

secret_in_state() {
  terraform -chdir="$CP_TF_DIR" state list | grep -E -q "^${SECRET_RESOURCE}(\\[|$)"
}

if secret_in_state; then
  echo "Secret already in Terraform state; skipping import."
else
  echo "Attempting to import secret into Terraform state (if it already exists)..."
  if ! terraform -chdir="$CP_TF_DIR" import "$SECRET_RESOURCE" "$SECRET_NAME" 2>&1 | tee "$IMPORT_OUTPUT" >/dev/null; then
    if secret_in_state || rg -E -q "Resource already managed by Terraform|Cannot import non-existent remote object|ResourceNotFoundException|resource does not exist" "$IMPORT_OUTPUT"; then
      echo "Secret import not required; continuing."
    else
      echo "Failed to import secret into Terraform state." >&2
      exit 1
    fi
  fi
fi

echo "Applying Terraform..."
terraform -chdir="$CP_TF_DIR" apply "$@"

if [[ "${SKIP_GH_SETUP:-0}" != "1" ]]; then
  if [[ -x "${ROOT_DIR}/scripts/setup-github-ci.sh" ]]; then
    echo "Syncing GitHub CI secrets/vars..."
    "${ROOT_DIR}/scripts/setup-github-ci.sh"
  else
    echo "GitHub CI setup script not found or not executable; skipping."
  fi
else
  echo "Skipping GitHub CI setup (SKIP_GH_SETUP=1)."
fi

if [[ "${SKIP_UI_DEPLOY:-0}" != "1" ]]; then
  UI_DEPLOY_SCRIPT="${ROOT_DIR}/control-plane/ui/scripts/deploy-ui-from-terraform.sh"
  if [[ -x "$UI_DEPLOY_SCRIPT" ]]; then
    echo "Deploying UI from Terraform outputs..."
    "$UI_DEPLOY_SCRIPT"
  else
    echo "UI deploy script not found or not executable; skipping."
  fi
else
  echo "Skipping UI deploy (SKIP_UI_DEPLOY=1)."
fi

read_output() {
  terraform -chdir="$CP_TF_DIR" output -raw "$1" 2>/dev/null || true
}

API_URL="$(read_output api_url)"
UI_URL="$(read_output ui_url)"
ALB_DNS="$(read_output alb_dns_name)"
UI_BUCKET_NAME="$(read_output ui_bucket_name)"
UI_CF_ID="$(read_output ui_cloudfront_distribution_id)"
SQS_URL="$(read_output sqs_queue_url)"

echo "Deployment complete."
echo "Summary:"
[[ -n "$API_URL" ]] && echo "  API URL: ${API_URL}"
[[ -n "$UI_URL" ]] && echo "  UI URL: ${UI_URL}"
[[ -n "$ALB_DNS" ]] && echo "  ALB DNS: ${ALB_DNS}"
[[ -n "$UI_BUCKET_NAME" ]] && echo "  UI bucket: ${UI_BUCKET_NAME}"
[[ -n "$UI_CF_ID" ]] && echo "  UI CloudFront ID: ${UI_CF_ID}"
[[ -n "$SQS_URL" ]] && echo "  SQS queue URL: ${SQS_URL}"
