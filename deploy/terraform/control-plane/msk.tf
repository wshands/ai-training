resource "aws_security_group" "msk" {
  count  = local.msk_enabled ? 1 : 0
  name   = "ai-platform-msk"
  vpc_id = module.vpc.vpc_id

  ingress {
    from_port       = var.msk_client_port
    to_port         = var.msk_client_port
    protocol        = "tcp"
    security_groups = [
      aws_security_group.control_plane_tasks.id,
      aws_security_group.event_processor_tasks.id
    ]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_msk_serverless_cluster" "this" {
  count        = local.msk_enabled ? 1 : 0
  cluster_name = "ai-platform-msk"

  client_authentication {
    sasl {
      iam {
        enabled = true
      }
    }
  }

  vpc_config {
    subnet_ids         = module.vpc.private_subnets
    security_group_ids = [aws_security_group.msk[0].id]
  }
}

data "aws_msk_bootstrap_brokers" "this" {
  count       = local.kafka_enabled && var.kafka_bootstrap == "" ? 1 : 0
  cluster_arn = local.msk_cluster_arn_value
}
