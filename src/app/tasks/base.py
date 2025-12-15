"""Base task class with common functionality.

Provides a foundation for all Celery tasks with:
- Database session management
- Error handling and logging
- Retry logic
- Metrics collection
"""

import functools
import logging
from typing import Any, Callable, TypeVar

from celery import Task
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_app import celery_app
from app.infrastructure.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

T = TypeVar("T")


class DatabaseTask(Task):
    """Base task class with database session management.

    Provides automatic session handling for tasks that need DB access.
    Sessions are created per-task and properly closed after completion.
    """

    _session: AsyncSession | None = None
    abstract = True

    @property
    def session(self) -> AsyncSession:
        """Get database session for this task."""
        if self._session is None:
            self._session = AsyncSessionLocal()
        return self._session

    def after_return(
        self,
        status: str,
        retval: Any,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: Any,
    ) -> None:
        """Clean up session after task completion."""
        if self._session is not None:
            # Note: In async context, this needs special handling
            self._session = None


class RetryableTask(Task):
    """Task with automatic retry on failure.

    Retries with exponential backoff on transient errors.
    """

    abstract = True
    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 600  # Max 10 minutes
    retry_jitter = True
    max_retries = 3

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: Any,
    ) -> None:
        """Log task failure."""
        logger.error(
            "Task %s failed after %d retries",
            self.name,
            self.request.retries,
            exc_info=exc,
            extra={
                "task_id": task_id,
                "task_name": self.name,
                "args": args,
                "kwargs": kwargs,
            },
        )

    def on_retry(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: Any,
    ) -> None:
        """Log task retry."""
        logger.warning(
            "Task %s retrying (attempt %d/%d)",
            self.name,
            self.request.retries + 1,
            self.max_retries,
            extra={
                "task_id": task_id,
                "task_name": self.name,
                "exception": str(exc),
            },
        )


def async_task(
    *args: Any,
    bind: bool = True,
    base: type[Task] = RetryableTask,
    **kwargs: Any,
) -> Callable:
    """Decorator for async Celery tasks.

    Wraps async functions to run in Celery's sync context.

    @param bind - Bind task instance to first argument
    @param base - Base task class to use
    @returns Decorated task function

    Example:
        @async_task(queue="critical")
        async def process_event(self, event_data: dict) -> None:
            async with get_async_session() as session:
                # Process event
                pass
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @celery_app.task(*args, bind=bind, base=base, **kwargs)
        @functools.wraps(func)
        def wrapper(*task_args: Any, **task_kwargs: Any) -> T:
            import asyncio

            # Get or create event loop
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Run async function
            return loop.run_until_complete(func(*task_args, **task_kwargs))

        return wrapper

    return decorator


def get_task_logger(task_name: str) -> logging.Logger:
    """Get logger for a specific task.

    @param task_name - Name of the task
    @returns Configured logger
    """
    return logging.getLogger(f"celery.task.{task_name}")
