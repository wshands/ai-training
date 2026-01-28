FROM python:3.11-slim
WORKDIR /app

COPY job-launcher/ /app/job-launcher/
COPY common/ /app/common/

RUN pip install --no-cache-dir -r /app/job-launcher/requirements.txt

ENV PYTHONPATH=/app:/app/job-launcher
CMD ["python", "/app/job-launcher/launcher.py"]
