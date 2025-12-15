#!/bin/bash
# Celery Worker Startup Script
# Usage: ./scripts/celery_worker.sh [queue_name] [concurrency]

set -e

QUEUE=${1:-"critical,high,normal,low"}
CONCURRENCY=${2:-4}
LOG_LEVEL=${LOG_LEVEL:-"INFO"}

echo "Starting Celery worker..."
echo "  Queues: $QUEUE"
echo "  Concurrency: $CONCURRENCY"
echo "  Log level: $LOG_LEVEL"

cd "$(dirname "$0")/.."

# Ensure PYTHONPATH includes src
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"

# Start worker
exec celery -A app.core.celery_app worker \
    --queues="$QUEUE" \
    --concurrency="$CONCURRENCY" \
    --loglevel="$LOG_LEVEL" \
    --hostname="worker@%h" \
    --prefetch-multiplier=4 \
    --max-tasks-per-child=1000
