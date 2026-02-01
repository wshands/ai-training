FROM python:3.11-slim
WORKDIR /app

COPY data-plane/ /app/data-plane/
COPY common/ /app/common/

RUN pip install --no-cache-dir -r /app/data-plane/requirements.txt

ENV PYTHONPATH=/app:/app/data-plane
CMD ["python", "/app/data-plane/launcher.py"]
