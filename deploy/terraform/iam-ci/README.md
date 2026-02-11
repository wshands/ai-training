# GitHub Actions IAM (OIDC)

This Terraform stack provisions:
- GitHub OIDC provider
- IAM role for ECR builds (`ai-training-github-ecr`)
- IAM role for UI deploys (`ai-training-github-ui`)

It is intended to be applied once and left alone (separate from the app infra).

## 1) Configure variables

```bash
cd deploy/terraform/iam-ci
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:
- `github_repo` (e.g., `wshands/ai-training`)
- `github_branches` (e.g., `["main","develop"]`)
- `ui_bucket_name`
- `ui_cloudfront_distribution_id`

## 2) Apply

```bash
terraform init
terraform apply
```

## 3) GitHub secrets

From `terraform output`:
- `ecr_role_arn` → set GitHub secret `AWS_ROLE_ARN`
- `ui_role_arn` → set GitHub secret `AWS_UI_ROLE_ARN`

Example (GitHub CLI):
```bash
gh secret set AWS_ROLE_ARN -b "$(terraform output -raw ecr_role_arn)"
gh secret set AWS_UI_ROLE_ARN -b "$(terraform output -raw ui_role_arn)"
```

## 4) GitHub Actions variables

Set these GitHub **Variables** (Repository → Settings → Secrets and variables → Actions → Variables):

- `AWS_REGION` (e.g., `us-west-2`)
- `UI_BUCKET` (S3 bucket name)
- `UI_CLOUDFRONT_DISTRIBUTION_ID`
- `REACT_APP_API_BASE_URL`
- `REACT_APP_WS_BASE_URL`
- `REACT_APP_CLERK_PUBLISHABLE_KEY`

## Notes
- The trust policy restricts access to your repo + branches.
- If you rename the repo or branches, update `github_repo`/`github_branches` and re-apply.
