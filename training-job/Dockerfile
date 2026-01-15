FROM python:3.11-slim

WORKDIR /opt/app

# Copy app code
COPY training-job/ /opt/app/

# Copy shared common package into the container
COPY common/ /opt/app/common/

RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

# Ensure Python can import from /opt/app (usually already true, but explicit is fine)
ENV PYTHONPATH=/opt/app

ENTRYPOINT ["python", "/opt/app/training_job_runner.py"]
