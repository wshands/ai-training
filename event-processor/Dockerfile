FROM python:3.11-slim
WORKDIR /app

COPY common /app/common

RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY event-processor /app/event-processor

RUN pip install --no-cache-dir -r /app/event-processor/requirements.txt

# Ensure Python can import from /app (usually already true, but explicit is fine)
ENV PYTHONPATH=/app

EXPOSE 5679

CMD ["python","-m","debugpy","--listen","0.0.0.0:5679","--wait-for-client","/app/event-processor/event_processor.py"]
