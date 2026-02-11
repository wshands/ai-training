#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IAM_TF_DIR="${ROOT_DIR}/deploy/terraform/iam-ci"
CP_TF_DIR="${ROOT_DIR}/deploy/terraform/control-plane"

export AWS_SDK_LOAD_CONFIG=1
export AWS_PROFILE="${AWS_PROFILE:-AdministratorAccess-230407893272}"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required. Install it first." >&2
  exit 1
fi

if [[ ! -d "$IAM_TF_DIR" ]]; then
  echo "Terraform IAM CI directory not found: $IAM_TF_DIR" >&2
  exit 1
fi

if [[ ! -d "$CP_TF_DIR" ]]; then
  echo "Terraform control-plane directory not found: $CP_TF_DIR" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI is not authenticated. Run: gh auth login" >&2
  exit 1
fi

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "AWS credentials not available. If using SSO, run:" >&2
  echo "  aws sso login --profile ${AWS_PROFILE}" >&2
  exit 1
fi

echo "Reading IAM CI outputs..."
ECR_ROLE_ARN="$(terraform -chdir="$IAM_TF_DIR" output -raw ecr_role_arn)"
UI_ROLE_ARN="$(terraform -chdir="$IAM_TF_DIR" output -raw ui_role_arn)"

echo "Setting GitHub secrets..."
gh secret set AWS_ROLE_ARN -b "$ECR_ROLE_ARN"
gh secret set AWS_UI_ROLE_ARN -b "$UI_ROLE_ARN"

echo "Reading control-plane outputs..."
UI_BUCKET="$(terraform -chdir="$CP_TF_DIR" output -raw ui_bucket_name)"
UI_CLOUDFRONT_DISTRIBUTION_ID="$(terraform -chdir="$CP_TF_DIR" output -raw ui_cloudfront_distribution_id)"

echo "Setting GitHub variables..."
gh variable set UI_BUCKET -b "$UI_BUCKET"
gh variable set UI_CLOUDFRONT_DISTRIBUTION_ID -b "$UI_CLOUDFRONT_DISTRIBUTION_ID"

echo "Done. Remember to set other UI variables (API/WS URLs, Clerk key)."
