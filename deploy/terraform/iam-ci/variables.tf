variable "region" {
  type        = string
  description = "AWS region"
  default     = "us-west-2"
}

variable "github_repo" {
  type        = string
  description = "GitHub repo in the form owner/name"
}

variable "github_branches" {
  type        = list(string)
  description = "Allowed branches for GitHub OIDC"
  default     = ["main", "develop"]
}

variable "github_oidc_thumbprints" {
  type        = list(string)
  description = "Thumbprints for token.actions.githubusercontent.com"
  default     = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

variable "ecr_repositories" {
  type        = list(string)
  description = "ECR repositories the role can manage"
  default     = ["ai-training/control-plane", "ai-training/event-processor"]
}

variable "ecr_role_name" {
  type        = string
  description = "IAM role name for ECR builds"
  default     = "ai-training-github-ecr"
}

variable "ecr_policy_name" {
  type        = string
  description = "IAM policy name for ECR builds"
  default     = "ai-training-github-ecr-policy"
}
