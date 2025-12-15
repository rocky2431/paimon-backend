"""Celery application configuration.

Provides task queue infrastructure with Redis broker for:
- Event processing (critical priority)
- Approval workflow (high priority)
- Scheduled tasks (normal priority)
- Background operations
"""

from celery import Celery
from kombu import Exchange, Queue

from app.core.config import get_settings

settings = get_settings()

# Create Celery application
celery_app = Celery(
    "paimon",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.event_tasks",
        "app.tasks.approval_tasks",
        "app.tasks.rebalance_tasks",
        "app.tasks.monitoring_tasks",
        "app.tasks.notification_tasks",
    ],
)

# Define exchanges
default_exchange = Exchange("default", type="direct")
priority_exchange = Exchange("priority", type="direct")

# Define queues with priorities
# Priority: critical (10) > high (5) > normal (0) > low (-5)
celery_app.conf.task_queues = (
    # Critical: Event processing, settlement
    Queue(
        "critical",
        exchange=priority_exchange,
        routing_key="critical",
        queue_arguments={"x-max-priority": 10},
    ),
    # High: Approval workflow, notifications
    Queue(
        "high",
        exchange=priority_exchange,
        routing_key="high",
        queue_arguments={"x-max-priority": 5},
    ),
    # Normal: Regular background tasks
    Queue(
        "normal",
        exchange=default_exchange,
        routing_key="normal",
        queue_arguments={"x-max-priority": 0},
    ),
    # Low: Reports, cleanup
    Queue(
        "low",
        exchange=default_exchange,
        routing_key="low",
        queue_arguments={"x-max-priority": -5},
    ),
)

# Default queue
celery_app.conf.task_default_queue = "normal"
celery_app.conf.task_default_exchange = "default"
celery_app.conf.task_default_routing_key = "normal"

# Task routing
celery_app.conf.task_routes = {
    # Critical tasks - event processing
    "app.tasks.event_tasks.*": {"queue": "critical"},
    # High priority - approvals and notifications
    "app.tasks.approval_tasks.*": {"queue": "high"},
    "app.tasks.notification_tasks.*": {"queue": "high"},
    # Normal - rebalancing and monitoring
    "app.tasks.rebalance_tasks.*": {"queue": "normal"},
    "app.tasks.monitoring_tasks.*": {"queue": "normal"},
}

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task execution
    task_acks_late=True,  # Acknowledge after task completes
    task_reject_on_worker_lost=True,  # Requeue if worker dies
    task_track_started=True,  # Track when task starts

    # Result backend
    result_expires=86400,  # Results expire after 24 hours
    result_extended=True,  # Store additional task metadata

    # Worker configuration
    worker_prefetch_multiplier=4,  # Prefetch 4 tasks per worker
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
    worker_disable_rate_limits=False,

    # Retry configuration
    task_default_retry_delay=60,  # 1 minute default retry delay
    task_max_retries=3,  # Default max retries

    # Logging
    worker_hijack_root_logger=False,  # Don't hijack root logger

    # Broker settings
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    broker_pool_limit=10,

    # Beat scheduler (for periodic tasks)
    beat_scheduler="celery.beat:PersistentScheduler",
    beat_schedule_filename=".celery-beat-schedule",
)

# Celery Beat schedule (periodic tasks)
celery_app.conf.beat_schedule = {
    # SLA check every minute
    "check-approval-sla": {
        "task": "app.tasks.approval_tasks.check_sla_deadlines",
        "schedule": 60.0,  # Every 60 seconds
        "options": {"queue": "high"},
    },
    # Settlement check every 5 minutes
    "check-pending-settlements": {
        "task": "app.tasks.event_tasks.check_pending_settlements",
        "schedule": 300.0,  # Every 5 minutes
        "options": {"queue": "critical"},
    },
    # Risk monitoring every minute
    "calculate-risk-metrics": {
        "task": "app.tasks.monitoring_tasks.calculate_risk_metrics",
        "schedule": 60.0,  # Every 60 seconds
        "options": {"queue": "normal"},
    },
    # Chain data sync every 30 seconds
    "sync-chain-state": {
        "task": "app.tasks.monitoring_tasks.sync_chain_state",
        "schedule": 30.0,  # Every 30 seconds
        "options": {"queue": "normal"},
    },
    # Health check every 30 seconds
    "health-check": {
        "task": "app.tasks.monitoring_tasks.health_check",
        "schedule": 30.0,  # Every 30 seconds
        "options": {"queue": "low"},
    },
    # Cleanup expired data daily at 2 AM
    "cleanup-expired-data": {
        "task": "app.tasks.monitoring_tasks.cleanup_expired_data",
        "schedule": {
            "hour": 2,
            "minute": 0,
        },
        "options": {"queue": "low"},
    },
    # Daily report generation at 8 AM
    "generate-daily-report": {
        "task": "app.tasks.monitoring_tasks.generate_daily_report",
        "schedule": {
            "hour": 8,
            "minute": 0,
        },
        "options": {"queue": "low"},
    },
}
