#!/usr/bin/env bash
#pulls the UI bucket + CloudFront distribution ID from Terraform outputs and deploys.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TF_DIR="$ROOT_DIR/deploy/terraform/control-plane"
UI_DIR="$ROOT_DIR/control-plane/ui"

if [[ ! -d "$TF_DIR" ]]; then
  echo "Terraform directory not found: $TF_DIR" >&2
  exit 1
fi

export AWS_PROFILE="${AWS_PROFILE:?Set AWS_PROFILE to your AWS SSO profile, e.g. AdministratorAccess-<account-id>}"
# WS_SDK_LOAD_CONFIG=1 tells AWS SDKs (and tools like Terraform via the SDK) to load the shared 
# config file ~/.aws/config in addition to ~/.aws/credentials.
# That’s important for SSO profiles, because SSO settings live in ~/.aws/config (not in ~/.aws/credentials).
# Without it, the SDK may ignore your SSO profile and fail to find credentials.
export AWS_SDK_LOAD_CONFIG=1

TF_OUTPUT_CMD=(terraform -chdir="$TF_DIR" output -raw)

if ! UI_BUCKET="$("${TF_OUTPUT_CMD[@]}" ui_bucket_name)"; then
  echo "Failed to read Terraform output ui_bucket_name. Ensure AWS creds are valid (e.g. run aws sso login)." >&2
  exit 1
fi

if ! UI_CLOUDFRONT_DISTRIBUTION_ID="$("${TF_OUTPUT_CMD[@]}" ui_cloudfront_distribution_id)"; then
  echo "Failed to read Terraform output ui_cloudfront_distribution_id. Ensure AWS creds are valid (e.g. run aws sso login)." >&2
  exit 1
fi

cd "$UI_DIR"
UI_BUCKET="$UI_BUCKET" UI_CLOUDFRONT_DISTRIBUTION_ID="$UI_CLOUDFRONT_DISTRIBUTION_ID" npm run deploy:clean:env
