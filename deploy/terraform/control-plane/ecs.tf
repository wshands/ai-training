locals {
  kafka_bootstrap_value = var.kafka_bootstrap != "" ? var.kafka_bootstrap : data.aws_msk_bootstrap_brokers.this.bootstrap_brokers_sasl_iam
  redis_url_value       = var.redis_url != "" ? var.redis_url : "redis://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0"
  kafka_security_protocol_value = var.kafka_security_protocol != "" ? var.kafka_security_protocol : "SASL_SSL"
  kafka_sasl_mechanism_value    = var.kafka_sasl_mechanism != "" ? var.kafka_sasl_mechanism : "AWS_MSK_IAM"
  postgres_dsn_secret_arn_value = var.postgres_dsn_secret_arn != "" ? var.postgres_dsn_secret_arn : aws_secretsmanager_secret.postgres_dsn.arn
  msk_cluster_arn_value         = var.msk_cluster_arn != "" ? var.msk_cluster_arn : aws_msk_serverless_cluster.this.arn
  msk_topic_arn                 = "${replace(local.msk_cluster_arn_value, ":cluster/", ":topic/")}/*"
  msk_group_arn                 = "${replace(local.msk_cluster_arn_value, ":cluster/", ":group/")}/*"

  common_env = merge(
    {
      KAFKA_BOOTSTRAP         = local.kafka_bootstrap_value
      KAFKA_TOPIC             = var.kafka_topic
      REDIS_URL               = local.redis_url_value
      KAFKA_SECURITY_PROTOCOL = local.kafka_security_protocol_value
      KAFKA_SASL_MECHANISM    = local.kafka_sasl_mechanism_value
      KAFKA_SSL_CA_FILE       = var.kafka_ssl_ca_file
      KAFKA_SSL_CERT_FILE     = var.kafka_ssl_cert_file
      KAFKA_SSL_KEY_FILE      = var.kafka_ssl_key_file
      LOG_LEVEL               = var.log_level
    },
    var.kafka_sasl_username_secret_arn == "" ? { KAFKA_SASL_USERNAME = var.kafka_sasl_username } : {},
    var.kafka_sasl_password_secret_arn == "" ? { KAFKA_SASL_PASSWORD = var.kafka_sasl_password } : {}
  )

  common_secrets = flatten([
    local.postgres_dsn_secret_arn_value != "" ? [{
      name      = "POSTGRES_DSN"
      valueFrom = local.postgres_dsn_secret_arn_value
    }] : [],
    var.kafka_sasl_username_secret_arn != "" ? [{
      name      = "KAFKA_SASL_USERNAME"
      valueFrom = var.kafka_sasl_username_secret_arn
    }] : [],
    var.kafka_sasl_password_secret_arn != "" ? [{
      name      = "KAFKA_SASL_PASSWORD"
      valueFrom = var.kafka_sasl_password_secret_arn
    }] : []
  ])

  secret_arns = [
    for arn in [
      local.postgres_dsn_secret_arn_value,
      var.kafka_sasl_username_secret_arn,
      var.kafka_sasl_password_secret_arn
    ] : arn if arn != ""
  ]

  control_plane_env = merge(local.common_env, {
    CLERK_JWKS_URL       = var.clerk_jwks_url
    CLERK_ISSUER         = var.clerk_issuer
    CLERK_AUDIENCE       = var.clerk_audience
    CLERK_JWT_ALGORITHM  = var.clerk_jwt_algorithm
    CONTROL_PLANE_ADMIN_TOKEN = var.control_plane_admin_token
    DATA_PLANE_TENANT_ID = var.data_plane_tenant_id
  })
}

resource "aws_ecs_cluster" "this" {
  name = "ai-platform-control-plane"
}

resource "aws_cloudwatch_log_group" "control_plane" {
  name              = "/ecs/control-plane"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "event_processor" {
  name              = "/ecs/event-processor"
  retention_in_days = 7
}

resource "aws_iam_role" "task_execution" {
  name               = "ai-platform-ecs-task-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
}

data "aws_iam_policy_document" "ecs_task_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "secrets_access" {
  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = local.secret_arns
  }
}

resource "aws_iam_policy" "secrets_access" {
  name   = "ai-platform-secrets-access"
  policy = data.aws_iam_policy_document.secrets_access.json
}

resource "aws_iam_role_policy_attachment" "task_execution_secrets_access" {
  role       = aws_iam_role.task_execution.name
  policy_arn = aws_iam_policy.secrets_access.arn
}

resource "aws_iam_role" "task" {
  name               = "ai-platform-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
}

data "aws_iam_policy_document" "msk_iam" {
  statement {
    effect = "Allow"
    actions = [
      "kafka-cluster:Connect",
      "kafka-cluster:DescribeCluster",
      "kafka-cluster:DescribeClusterV2",
    ]
    resources = [local.msk_cluster_arn_value]
  }

  statement {
    effect = "Allow"
    actions = [
      "kafka-cluster:CreateTopic",
      "kafka-cluster:DescribeTopic",
      "kafka-cluster:ReadData",
      "kafka-cluster:WriteData",
    ]
    resources = [local.msk_topic_arn]
  }

  statement {
    effect = "Allow"
    actions = [
      "kafka-cluster:DescribeGroup",
      "kafka-cluster:AlterGroup",
    ]
    resources = [local.msk_group_arn]
  }
}

resource "aws_iam_policy" "msk_iam" {
  name   = "ai-platform-msk-iam"
  policy = data.aws_iam_policy_document.msk_iam.json
}

resource "aws_iam_role_policy_attachment" "task_msk_iam" {
  role       = aws_iam_role.task.name
  policy_arn = aws_iam_policy.msk_iam.arn
}

resource "aws_ecs_task_definition" "control_plane" {
  family                   = "control-plane"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = "control-plane"
      image     = var.control_plane_image
      essential = true
      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]
      environment = [
        for k, v in local.control_plane_env : {
          name  = k
          value = v
        }
      ]
      secrets = local.common_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.control_plane.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "control-plane"
        }
      }
    }
  ])
}

resource "aws_ecs_task_definition" "event_processor" {
  family                   = "event-processor"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = "event-processor"
      image     = var.event_processor_image
      essential = true
      environment = [
        for k, v in local.common_env : {
          name  = k
          value = v
        }
      ]
      secrets = local.common_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.event_processor.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "event-processor"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "control_plane" {
  name            = "control-plane"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.control_plane.arn
  desired_count   = var.control_plane_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = module.vpc.private_subnets
    security_groups = [aws_security_group.control_plane_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.control_plane.arn
    container_name   = "control-plane"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.http, aws_lb_listener.https]
}

resource "aws_ecs_service" "event_processor" {
  name            = "event-processor"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.event_processor.arn
  desired_count   = var.event_processor_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = module.vpc.private_subnets
    security_groups = [aws_security_group.event_processor_tasks.id]
    assign_public_ip = false
  }
}
