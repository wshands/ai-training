locals {
  common_env = merge(
    {
      KAFKA_BOOTSTRAP         = var.kafka_bootstrap
      KAFKA_TOPIC             = var.kafka_topic
      REDIS_URL               = var.redis_url
      KAFKA_SECURITY_PROTOCOL = var.kafka_security_protocol
      KAFKA_SASL_MECHANISM    = var.kafka_sasl_mechanism
      KAFKA_SSL_CA_FILE       = var.kafka_ssl_ca_file
      KAFKA_SSL_CERT_FILE     = var.kafka_ssl_cert_file
      KAFKA_SSL_KEY_FILE      = var.kafka_ssl_key_file
      LOG_LEVEL               = var.log_level
    },
    var.postgres_dsn_secret_arn == "" ? { POSTGRES_DSN = var.postgres_dsn } : {},
    var.kafka_sasl_username_secret_arn == "" ? { KAFKA_SASL_USERNAME = var.kafka_sasl_username } : {},
    var.kafka_sasl_password_secret_arn == "" ? { KAFKA_SASL_PASSWORD = var.kafka_sasl_password } : {}
  )

  common_secrets = flatten([
    var.postgres_dsn_secret_arn != "" ? [{
      name      = "POSTGRES_DSN"
      valueFrom = var.postgres_dsn_secret_arn
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
      var.postgres_dsn_secret_arn,
      var.kafka_sasl_username_secret_arn,
      var.kafka_sasl_password_secret_arn
    ] : arn if arn != ""
  ]

  control_plane_env = merge(local.common_env, {
    CLERK_JWKS_URL       = var.clerk_jwks_url
    CLERK_ISSUER         = var.clerk_issuer
    CLERK_AUDIENCE       = var.clerk_audience
    CLERK_JWT_ALGORITHM  = var.clerk_jwt_algorithm
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
  count = length(local.secret_arns) > 0 ? 1 : 0
  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = local.secret_arns
  }
}

resource "aws_iam_policy" "secrets_access" {
  count  = length(local.secret_arns) > 0 ? 1 : 0
  name   = "ai-platform-secrets-access"
  policy = data.aws_iam_policy_document.secrets_access[0].json
}

resource "aws_iam_role_policy_attachment" "task_execution_secrets_access" {
  count      = length(local.secret_arns) > 0 ? 1 : 0
  role       = aws_iam_role.task_execution.name
  policy_arn = aws_iam_policy.secrets_access[0].arn
}

resource "aws_iam_role" "task" {
  name               = "ai-platform-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
}

data "aws_iam_policy_document" "msk_iam" {
  count = var.msk_cluster_arn != "" ? 1 : 0
  statement {
    effect = "Allow"
    actions = [
      "kafka-cluster:Connect",
      "kafka-cluster:DescribeCluster",
      "kafka-cluster:DescribeClusterV2",
      "kafka-cluster:DescribeTopic",
      "kafka-cluster:DescribeGroup",
      "kafka-cluster:ReadData",
      "kafka-cluster:WriteData",
      "kafka-cluster:AlterGroup",
    ]
    resources = [
      var.msk_cluster_arn,
      "${var.msk_cluster_arn}/*",
    ]
  }
}

resource "aws_iam_policy" "msk_iam" {
  count  = var.msk_cluster_arn != "" ? 1 : 0
  name   = "ai-platform-msk-iam"
  policy = data.aws_iam_policy_document.msk_iam[0].json
}

resource "aws_iam_role_policy_attachment" "task_msk_iam" {
  count      = var.msk_cluster_arn != "" ? 1 : 0
  role       = aws_iam_role.task.name
  policy_arn = aws_iam_policy.msk_iam[0].arn
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
