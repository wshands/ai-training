FROM python:3.11-slim
WORKDIR /app

COPY common /app/common

RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY control-plane/event-processor /app/event-processor

RUN pip install --no-cache-dir -r /app/event-processor/requirements.txt

# Ensure Python can import from /app (usually already true, but explicit is fine)
ENV PYTHONPATH=/app

EXPOSE 5679

COPY control-plane/event-processor/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
