variable "region" {
  type        = string
  description = "AWS region"
  default     = "us-west-2"
}

variable "aws_profile" {
  type        = string
  description = "AWS Identity Center SSO profile to use"
  default     = ""
}

variable "control_plane_image" {
  type        = string
  description = "ECR image for the control-plane API"
  default     = "ai-training-control-plane:latest"
}

variable "event_processor_image" {
  type        = string
  description = "ECR image for the event-processor"
  default     = "ai-training-event-processor:latest"
}

variable "control_plane_desired_count" {
  type        = number
  description = "Number of control-plane tasks"
  default     = 1
}

variable "event_processor_desired_count" {
  type        = number
  description = "Number of event-processor tasks"
  default     = 1
}

variable "event_bus_provider" {
  type        = string
  description = "Event bus provider (kafka or sqs)"
  default     = "sqs"
}

variable "sqs_queue_name" {
  type        = string
  description = "SQS FIFO queue name for job events"
  default     = "job-events.fifo"
}

variable "kafka_bootstrap" {
  type        = string
  description = "Kafka bootstrap servers"
  default     = ""
}

variable "kafka_topic" {
  type        = string
  description = "Kafka topic for job events"
  default     = "job-events"
}

variable "postgres_dsn" {
  type        = string
  description = "Postgres DSN for control-plane"
  sensitive   = true
  default     = ""
}

variable "postgres_dsn_secret_arn" {
  type        = string
  description = "Secrets Manager ARN for POSTGRES_DSN (optional)"
  default     = ""
}

variable "redis_url" {
  type        = string
  description = "Redis connection URL"
  sensitive   = true
  default     = ""
}

variable "log_level" {
  type        = string
  description = "Log level for services"
  default     = "INFO"
}

variable "clerk_jwks_url" {
  type        = string
  description = "Clerk JWKS URL"
  default     = ""
}

variable "clerk_issuer" {
  type        = string
  description = "Clerk issuer"
  default     = ""
}

variable "clerk_audience" {
  type        = string
  description = "Clerk audience"
  default     = ""
}

variable "clerk_jwt_algorithm" {
  type        = string
  description = "JWT algorithm"
  default     = "RS256"
}

variable "control_plane_admin_token" {
  type        = string
  description = "Admin token for control-plane internal admin endpoints"
  sensitive   = true
  default     = ""
}

variable "kafka_security_protocol" {
  type        = string
  description = "Kafka security protocol (e.g. SASL_SSL)"
  default     = ""
}

variable "kafka_sasl_mechanism" {
  type        = string
  description = "Kafka SASL mechanism (e.g. SCRAM-SHA-512)"
  default     = ""
}

variable "kafka_sasl_username" {
  type        = string
  description = "Kafka SASL username"
  default     = ""
}

variable "kafka_sasl_password" {
  type        = string
  description = "Kafka SASL password"
  sensitive   = true
  default     = ""
}

variable "kafka_sasl_username_secret_arn" {
  type        = string
  description = "Secrets Manager ARN for KAFKA_SASL_USERNAME (optional)"
  default     = ""
}

variable "kafka_sasl_password_secret_arn" {
  type        = string
  description = "Secrets Manager ARN for KAFKA_SASL_PASSWORD (optional)"
  default     = ""
}

variable "kafka_ssl_ca_file" {
  type        = string
  description = "Path to Kafka SSL CA file in the task"
  default     = ""
}

variable "kafka_ssl_cert_file" {
  type        = string
  description = "Path to Kafka SSL cert file in the task"
  default     = ""
}

variable "kafka_ssl_key_file" {
  type        = string
  description = "Path to Kafka SSL key file in the task"
  default     = ""
}

variable "data_plane_tenant_id" {
  type        = string
  description = "Optional tenant ID to restrict data-plane access"
  default     = ""
}

variable "alb_certificate_arn" {
  type        = string
  description = "ACM certificate ARN for HTTPS listener (optional)"
  default     = ""
}

variable "msk_cluster_arn" {
  type        = string
  description = "MSK cluster ARN for IAM auth policy (optional)"
  default     = ""
}

variable "msk_client_port" {
  type        = number
  description = "MSK serverless client port"
  default     = 9098
}

variable "postgres_engine_version" {
  type        = string
  description = "Postgres engine version"
  default     = "18.1"
}

variable "postgres_instance_class" {
  type        = string
  description = "Postgres instance class"
  default     = "db.t4g.small"
}

variable "postgres_allocated_storage" {
  type        = number
  description = "Postgres allocated storage (GB)"
  default     = 50
}

variable "postgres_db_name" {
  type        = string
  description = "Postgres database name"
  default     = "controlplane"
}

variable "postgres_username" {
  type        = string
  description = "Postgres username"
  default     = "controlplane"
}

variable "postgres_snapshot_identifier" {
  type        = string
  description = "RDS snapshot identifier to restore from (optional)"
  default     = ""
}

variable "postgres_final_snapshot_enabled" {
  type        = bool
  description = "Create a final snapshot on destroy"
  default     = true
}

variable "ui_bucket_name" {
  type        = string
  description = "S3 bucket name for the UI (optional, auto-generated if empty)"
  default     = ""
}

variable "ui_domain_name" {
  type        = string
  description = "Custom domain name for the UI (e.g. ui.example.com)"
  default     = ""
}

variable "ui_domain_names" {
  type        = list(string)
  description = "Custom domain names for the UI (e.g. [\"example.com\", \"www.example.com\"])"
  default     = []
}

variable "ui_hosted_zone_id" {
  type        = string
  description = "Route53 hosted zone ID for ui_domain_name"
  default     = ""
}

variable "ui_cloudfront_price_class" {
  type        = string
  description = "CloudFront price class for the UI distribution"
  default     = "PriceClass_100"
}

variable "api_domain_name" {
  type        = string
  description = "Custom domain name for the API (e.g. api.example.com)"
  default     = ""
}

variable "api_hosted_zone_id" {
  type        = string
  description = "Route53 hosted zone ID for api_domain_name"
  default     = ""
}

variable "postgres_multi_az" {
  type        = bool
  description = "Enable Multi-AZ for Postgres"
  default     = false
}

variable "redis_node_type" {
  type        = string
  description = "ElastiCache node type"
  default     = "cache.t4g.small"
}

variable "redis_engine_version" {
  type        = string
  description = "ElastiCache Redis engine version"
  default     = "7.1"
}
