"""Celery tasks for background processing.

This module provides async task execution for:
- Event processing from blockchain
- Approval workflow management
- Rebalancing operations
- Risk monitoring
- Notifications
"""

from app.core.celery_app import celery_app

__all__ = ["celery_app"]
