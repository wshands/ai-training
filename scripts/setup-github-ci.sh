#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IAM_TF_DIR="${ROOT_DIR}/deploy/terraform/iam-ci"
CP_TF_DIR="${ROOT_DIR}/deploy/terraform/control-plane"

export AWS_SDK_LOAD_CONFIG=1
export AWS_PROFILE="${AWS_PROFILE:?Set AWS_PROFILE to your AWS SSO profile, e.g. AdministratorAccess-<account-id>}"

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

echo "Setting GitHub secrets..."
gh secret set AWS_ROLE_ARN -b "$ECR_ROLE_ARN"

echo "Done."
