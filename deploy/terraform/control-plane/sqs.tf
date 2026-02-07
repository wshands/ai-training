locals {
  sqs_queue_name = var.sqs_queue_name != "" ? var.sqs_queue_name : "job-events.fifo"
  sqs_dlq_name   = "${replace(local.sqs_queue_name, ".fifo", "")}-dlq.fifo"
}

resource "aws_sqs_queue" "events_dlq" {
  count = local.sqs_enabled ? 1 : 0

  name                        = local.sqs_dlq_name
  fifo_queue                  = true
  content_based_deduplication = false
  deduplication_scope         = "messageGroup"
  fifo_throughput_limit       = "perMessageGroupId"
}

resource "aws_sqs_queue" "events" {
  count = local.sqs_enabled ? 1 : 0

  name                        = local.sqs_queue_name
  fifo_queue                  = true
  content_based_deduplication = false
  deduplication_scope         = "messageGroup"
  fifo_throughput_limit       = "perMessageGroupId"
  visibility_timeout_seconds  = 60

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.events_dlq[0].arn
    maxReceiveCount     = 5
  })
}
