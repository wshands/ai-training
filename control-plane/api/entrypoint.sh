#!/bin/sh
set -e

if [ "${WAIT_FOR_DEBUGGER:-0}" = "1" ]; then
  exec python -m debugpy --listen 0.0.0.0:5678 --wait-for-client \
    -m uvicorn app.main:app --host 0.0.0.0 --port 8000
fi

exec python -m debugpy --listen 0.0.0.0:5678 \
  -m uvicorn app.main:app --host 0.0.0.0 --port 8000
