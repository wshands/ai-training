FROM python:3.11-slim
WORKDIR /opt/app
COPY . /opt/app
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt
ENTRYPOINT ["python", "/opt/app/training_job_runner.py"]
