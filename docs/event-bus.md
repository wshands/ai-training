# Event Bus (SQS FIFO default)

The control-plane publishes job lifecycle events to an event bus. This repo
supports:

- **SQS FIFO (default)**: simple, lower cost, per-job ordering via MessageGroupId
- **Kafka/MSK**: optional, higher throughput/retention

## Local dev with ElasticMQ (SQS-compatible)

ElasticMQ is a lightweight, local SQS-compatible server that works with FIFO
queues. Use it to run the SQS path on your laptop.

### 1) Start ElasticMQ

Using Docker:

```bash
docker run --rm -p 9324:9324 -p 9325:9325 softwaremill/elasticmq-native
```

This exposes:
- SQS endpoint: `http://localhost:9324`
- Web UI: `http://localhost:9325` (optional)

### 2) Create the FIFO queue

```bash
aws --endpoint-url=http://localhost:9324 sqs create-queue \
  --queue-name job-events.fifo \
  --attributes FifoQueue=true,ContentBasedDeduplication=false,DeduplicationScope=messageGroup,FifoThroughputLimit=perMessageGroupId
```

Grab the queue URL from the output and set it as `SQS_QUEUE_URL`.

### 3) Configure the services

Set these env vars for the control-plane and event-processor:

```bash
EVENT_BUS_PROVIDER=sqs
SQS_ENDPOINT_URL=http://localhost:9324
SQS_QUEUE_URL=http://localhost:9324/queue/job-events.fifo
```

Notes:
- FIFO requires queue names to end with `.fifo`.
- The control-plane sends `MessageGroupId = job_id` and
  `MessageDeduplicationId = event_id` to preserve per-job ordering.

## Kafka/MSK (optional)

To use Kafka/MSK instead of SQS, set:

```bash
EVENT_BUS_PROVIDER=kafka
KAFKA_BOOTSTRAP=...
KAFKA_TOPIC=job-events
```

The Terraform toggle `event_bus_provider` controls which resources are
provisioned in AWS.
