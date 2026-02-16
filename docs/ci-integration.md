# CI Integration: IAM, Setup Script, and Workflows

This repo uses a small, explicit chain of responsibility to wire AWS IAM to
GitHub Actions without static credentials.

## 1) Terraform IAM stack (`deploy/terraform/iam-ci/`)
This stack provisions:
- The GitHub OIDC provider
- An ECR build role (for image pushes)

Outputs:
- `ecr_role_arn`

This is the **role ARN** the workflows assume.

## 2) Setup script (`scripts/setup-github-ci.sh`)
The helper script reads Terraform outputs and pushes them into GitHub:

- **Secrets**
  - `AWS_ROLE_ARN` (from `ecr_role_arn`)

This keeps the workflows fully automated without manual copying.

Run it once when you first set up CI. Re-run it after any Terraform
destroy/apply that changes IAM role ARNs.

## 3) GitHub Actions workflows (`.github/workflows`)
Workflows consume those values:

- `build-and-push-ecr.yml`
  - Assumes `AWS_ROLE_ARN`
  - Builds + pushes control-plane & event-processor images to ECR

Also set the GitHub **variable** `AWS_REGION` (e.g., `us-west-2`) for the workflow.

## TL;DR
- **Terraform** creates IAM roles.
- **Setup script** syncs Terraform outputs into GitHub secrets.
- **Workflows** use those secrets to run with OIDC.
