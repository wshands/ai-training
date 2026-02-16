# CI Integration: IAM, Setup Script, and Workflows

This repo uses a small, explicit chain of responsibility to wire AWS IAM to
GitHub Actions without static credentials.

## 1) Terraform IAM stack (`deploy/terraform/iam-ci/`)
This stack provisions:
- The GitHub OIDC provider
- An ECR build role (for image pushes)
- A UI deploy role (for S3 sync + CloudFront invalidation)

Outputs:
- `ecr_role_arn`
- `ui_role_arn`

These are the **role ARNs** the workflows assume.

## 2) Setup script (`scripts/setup-github-ci.sh`)
The helper script reads Terraform outputs and pushes them into GitHub:

- **Secrets**
  - `AWS_ROLE_ARN` (from `ecr_role_arn`)
  - `AWS_UI_ROLE_ARN` (from `ui_role_arn`)
- **Variables**
  - `UI_BUCKET` (from `ui_bucket_name` in the control-plane stack)
  - `UI_CLOUDFRONT_DISTRIBUTION_ID` (from `ui_cloudfront_distribution_id`)

This keeps the workflows fully automated without manual copying.

Run it once when you first set up CI. Re-run it after any Terraform
destroy/apply that changes IAM role ARNs, UI bucket name, or CloudFront
distribution ID.

## 3) GitHub Actions workflows (`.github/workflows`)
Two workflows consume those values:

- `build-and-push-ecr.yml`
  - Assumes `AWS_ROLE_ARN`
  - Builds + pushes control-plane & event-processor images to ECR

- `deploy-ui.yml`
  - Assumes `AWS_UI_ROLE_ARN`
  - Uses `UI_BUCKET` + `UI_CLOUDFRONT_DISTRIBUTION_ID`
  - Builds and deploys the UI

## TL;DR
- **Terraform** creates IAM roles.
- **Setup script** syncs Terraform outputs into GitHub secrets/vars.
- **Workflows** use those secrets/vars to run with OIDC.
