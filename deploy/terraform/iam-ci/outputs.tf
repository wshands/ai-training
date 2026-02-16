output "github_oidc_provider_arn" {
  description = "GitHub OIDC provider ARN"
  value       = aws_iam_openid_connect_provider.github.arn
}

output "ecr_role_arn" {
  description = "Role ARN for ECR builds"
  value       = aws_iam_role.ecr.arn
}
