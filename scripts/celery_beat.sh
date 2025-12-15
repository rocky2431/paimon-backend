#!/bin/bash
# Celery Beat Scheduler Startup Script
# Usage: ./scripts/celery_beat.sh

set -e

LOG_LEVEL=${LOG_LEVEL:-"INFO"}

echo "Starting Celery Beat scheduler..."
echo "  Log level: $LOG_LEVEL"

cd "$(dirname "$0")/.."

# Ensure PYTHONPATH includes src
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"

# Start beat scheduler
exec celery -A app.core.celery_app beat \
    --loglevel="$LOG_LEVEL" \
    --scheduler=celery.beat:PersistentScheduler
