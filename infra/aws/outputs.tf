output "alb_dns_name" {
  description = "ALB DNS name for control-plane"
  value       = aws_lb.control_plane.dns_name
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.this.name
}

output "msk_bootstrap_brokers" {
  description = "MSK bootstrap brokers (SASL IAM)"
  value       = data.aws_msk_bootstrap_brokers.this.bootstrap_brokers_sasl_iam
}

output "msk_cluster_arn" {
  description = "MSK cluster ARN"
  value       = aws_msk_serverless_cluster.this.arn
}

output "redis_primary_endpoint" {
  description = "ElastiCache Redis primary endpoint"
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "postgres_endpoint" {
  description = "Postgres endpoint"
  value       = aws_db_instance.postgres.address
}

output "postgres_dsn_secret_arn" {
  description = "Secrets Manager ARN for POSTGRES_DSN"
  value       = aws_secretsmanager_secret.postgres_dsn.arn
}
