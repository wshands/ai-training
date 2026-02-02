FROM python:3.11-slim
WORKDIR /app

COPY data-plane/launcher/ /app/launcher/
COPY common/ /app/common/

RUN pip install --no-cache-dir -r /app/launcher/requirements.txt

ENV PYTHONPATH=/app:/app/launcher
CMD ["python", "/app/launcher/launcher.py"]
