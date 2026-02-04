resource "aws_secretsmanager_secret" "postgres_dsn" {
  name = "ai-platform/postgres-dsn"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_secretsmanager_secret_version" "postgres_dsn" {
  secret_id     = aws_secretsmanager_secret.postgres_dsn.id
  secret_string = "postgresql://${var.postgres_username}:${random_password.postgres.result}@${aws_db_instance.postgres.address}:${aws_db_instance.postgres.port}/${var.postgres_db_name}"
}
