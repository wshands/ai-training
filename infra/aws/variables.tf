variable "region" {
  type        = string
  description = "AWS region"
  default     = "us-west-2"
}

variable "control_plane_image" {
  type        = string
  description = "ECR image for the control-plane API"
  default     = "ai-platform-d-control-plane:latest"
}

variable "event_processor_image" {
  type        = string
  description = "ECR image for the event-processor"
  default     = "ai-platform-d-event-processor:latest"
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

variable "kafka_bootstrap" {
  type        = string
  description = "Kafka bootstrap servers"
  default     = "kafka:9092"
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
  default     = "postgresql://postgres:postgres@postgres:5432/controlplane"
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
  default     = "redis://redis:6379/0"
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
