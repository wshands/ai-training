#!/bin/sh
set -e

if [ "${WAIT_FOR_DEBUGGER:-0}" = "1" ]; then
  exec python -m debugpy --listen 0.0.0.0:5679 --wait-for-client \
    /app/event-processor/event_processor.py
fi

exec python -m debugpy --listen 0.0.0.0:5679 \
  /app/event-processor/event_processor.py
