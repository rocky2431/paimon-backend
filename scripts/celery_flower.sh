#!/bin/bash
# Celery Flower Monitoring Dashboard Startup Script
# Usage: ./scripts/celery_flower.sh [port]

set -e

PORT=${1:-5555}

echo "Starting Celery Flower dashboard..."
echo "  Port: $PORT"

cd "$(dirname "$0")/.."

# Ensure PYTHONPATH includes src
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"

# Start flower
exec celery -A app.core.celery_app flower \
    --port="$PORT" \
    --broker_api="redis://localhost:6379/0"
