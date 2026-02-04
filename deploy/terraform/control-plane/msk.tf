resource "aws_security_group" "msk" {
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
    security_group_ids = [aws_security_group.msk.id]
  }
}

data "aws_msk_bootstrap_brokers" "this" {
  cluster_arn = aws_msk_serverless_cluster.this.arn
}
