output "alb_dns_name" {
  description = "ALB DNS name for control-plane"
  value       = aws_lb.control_plane.dns_name
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.this.name
}
