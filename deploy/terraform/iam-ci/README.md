# GitHub Actions IAM (OIDC)

This Terraform stack provisions:
- GitHub OIDC provider
- IAM role for ECR builds (`ai-training-github-ecr`)

It is intended to be applied once and left alone (separate from the app infra).

## 1) Configure variables

```bash
cd deploy/terraform/iam-ci
```

Provide variables either via `terraform.tfvars` or `-var` flags:
- `github_repo` (e.g., `wshands/ai-training`)
- `github_branches` (e.g., `["main","develop"]`)

## 2) Apply

```bash
terraform init
terraform apply -var "github_repo=wshands/ai-training"
```

## 3) GitHub secrets

From `terraform output`:
- `ecr_role_arn` → set GitHub secret `AWS_ROLE_ARN`

Example (GitHub CLI):
```bash
gh secret set AWS_ROLE_ARN -b "$(terraform output -raw ecr_role_arn)"
```

## 4) GitHub Actions variables

Set these GitHub **Variables** (Repository → Settings → Secrets and variables → Actions → Variables):

- `AWS_REGION` (e.g., `us-west-2`)

## Notes
- The trust policy restricts access to your repo + branches.
- If you rename the repo or branches, update `github_repo`/`github_branches` and re-apply.
