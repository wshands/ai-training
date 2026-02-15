resource "aws_security_group" "postgres" {
  name   = "ai-platform-postgres"
  vpc_id = module.vpc.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
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

resource "aws_db_subnet_group" "postgres" {
  name       = "ai-platform-postgres"
  subnet_ids = module.vpc.private_subnets
}

resource "random_password" "postgres" {
  length  = 24
  special = false
}

resource "random_id" "postgres_final_snapshot" {
  byte_length = 4
}

locals {
  postgres_restore_from_snapshot = var.postgres_snapshot_identifier != ""
}

resource "aws_db_instance" "postgres" {
  identifier              = "ai-platform-postgres"
  engine                  = "postgres"
  engine_version          = var.postgres_engine_version
  instance_class          = var.postgres_instance_class
  allocated_storage       = var.postgres_allocated_storage
  db_name                 = local.postgres_restore_from_snapshot ? null : var.postgres_db_name
  username                = local.postgres_restore_from_snapshot ? null : var.postgres_username
  password                = local.postgres_restore_from_snapshot ? null : random_password.postgres.result
  snapshot_identifier     = local.postgres_restore_from_snapshot ? var.postgres_snapshot_identifier : null
  db_subnet_group_name    = aws_db_subnet_group.postgres.name
  vpc_security_group_ids  = [aws_security_group.postgres.id]
  multi_az                = var.postgres_multi_az
  publicly_accessible     = false
  deletion_protection     = false
  skip_final_snapshot     = var.postgres_final_snapshot_enabled ? false : true
  final_snapshot_identifier = var.postgres_final_snapshot_enabled ? "ai-platform-postgres-final-${random_id.postgres_final_snapshot.hex}" : null
  backup_retention_period = 7
}
