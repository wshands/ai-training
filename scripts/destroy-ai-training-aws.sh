#!/usr/bin/env bash
# Run from anywhere; the script resolves paths relative to its own location.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CP_TF_DIR="${ROOT_DIR}/deploy/terraform/control-plane"
SECRET_RESOURCE="aws_secretsmanager_secret.postgres_dsn"

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

read -r -p "This will remove the control-plane stack, empty the UI bucket, and run terraform destroy. Continue? [y/N] " CONFIRM
case "${CONFIRM}" in
  y|Y) ;;
  *) echo "Aborted."; exit 1 ;;
esac

echo "Initializing Terraform..."
terraform -chdir="$CP_TF_DIR" init

STATE_LIST="$(terraform -chdir="$CP_TF_DIR" state list)"

# Best-effort removal of common addresses (ignore if not present).
terraform -chdir="$CP_TF_DIR" state rm aws_secretsmanager_secret.postgres_dsn >/dev/null 2>&1 || true
terraform -chdir="$CP_TF_DIR" state rm aws_secretsmanager_secret_version.postgres_dsn >/dev/null 2>&1 || true

STATE_LIST="$(terraform -chdir="$CP_TF_DIR" state list)"
if command -v rg >/dev/null 2>&1; then
  SECRET_STATE_MATCHES="$(printf '%s\n' "$STATE_LIST" | rg 'aws_secretsmanager_secret(_version)?\\.postgres_dsn' || true)"
else
  SECRET_STATE_MATCHES="$(printf '%s\n' "$STATE_LIST" | grep -E 'aws_secretsmanager_secret(_version)?\\.postgres_dsn' || true)"
fi
if [[ -n "$SECRET_STATE_MATCHES" ]]; then
  echo "Removing postgres DSN secret from Terraform state..."
  while IFS= read -r RES; do
    [[ -z "$RES" ]] && continue
    terraform -chdir="$CP_TF_DIR" state rm "$RES"
  done <<< "$SECRET_STATE_MATCHES"
else
  echo "Postgres DSN secret not in state; skipping state rm."
fi

STATE_LIST="$(terraform -chdir="$CP_TF_DIR" state list)"
if command -v rg >/dev/null 2>&1; then
  REMAINING_MATCHES="$(printf '%s\n' "$STATE_LIST" | rg 'aws_secretsmanager_secret(_version)?\\.postgres_dsn' || true)"
else
  REMAINING_MATCHES="$(printf '%s\n' "$STATE_LIST" | grep -E 'aws_secretsmanager_secret(_version)?\\.postgres_dsn' || true)"
fi
if [[ -n "$REMAINING_MATCHES" ]]; then
  echo "Postgres DSN secret still present in state; aborting destroy." >&2
  printf '%s\n' "$REMAINING_MATCHES" >&2
  exit 1
fi

UI_BUCKET="$(terraform -chdir="$CP_TF_DIR" output -raw ui_bucket_name 2>/dev/null || true)"
if [[ -n "$UI_BUCKET" ]]; then
  echo "Emptying UI bucket: $UI_BUCKET"
  aws s3 rm "s3://${UI_BUCKET}" --recursive >/dev/null 2>&1 || true

  VERSIONS_JSON="$(mktemp)"
  MARKERS_JSON="$(mktemp)"

  VERSION_COUNT="$(aws s3api list-object-versions --bucket "$UI_BUCKET" --query 'length(Versions || `[]`)' --output text)"
  if [[ "$VERSION_COUNT" != "0" ]]; then
    aws s3api list-object-versions \
      --bucket "$UI_BUCKET" \
      --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' \
      --output json > "$VERSIONS_JSON"
    aws s3api delete-objects --bucket "$UI_BUCKET" --delete "file://${VERSIONS_JSON}" >/dev/null
  fi

  MARKER_COUNT="$(aws s3api list-object-versions --bucket "$UI_BUCKET" --query 'length(DeleteMarkers || `[]`)' --output text)"
  if [[ "$MARKER_COUNT" != "0" ]]; then
    aws s3api list-object-versions \
      --bucket "$UI_BUCKET" \
      --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' \
      --output json > "$MARKERS_JSON"
    aws s3api delete-objects --bucket "$UI_BUCKET" --delete "file://${MARKERS_JSON}" >/dev/null
  fi

  rm -f "$VERSIONS_JSON" "$MARKERS_JSON"
else
  echo "UI bucket output not found; skipping bucket cleanup."
fi

echo "Destroying Terraform resources..."
terraform -chdir="$CP_TF_DIR" destroy "$@"

echo "Destroy complete."
