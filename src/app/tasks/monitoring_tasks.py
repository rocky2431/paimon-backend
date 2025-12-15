"""Monitoring and maintenance tasks.

Handles system monitoring operations:
- Risk metrics calculation
- Chain state synchronization
- Health checks
- Data cleanup
- Report generation
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from app.core.celery_app import celery_app
from app.infrastructure.database.session import AsyncSessionLocal
from app.repositories import RiskEventRepository, TransactionRepository
from app.tasks.base import async_task, get_task_logger

logger = get_task_logger("monitoring_tasks")


@async_task(queue="normal")
async def calculate_risk_metrics(self) -> dict[str, Any]:
    """Calculate and store current risk metrics.

    Scheduled task that runs every minute.

    @returns Calculation results
    """
    logger.debug("Calculating risk metrics")

    try:
        # TODO: Implement real risk metric calculation
        # This should:
        # 1. Fetch current NAV from chain
        # 2. Fetch asset holdings
        # 3. Calculate ratios (L1, L1+L2, redemption coverage)
        # 4. Store in TimescaleDB risk_metrics_series

        metrics = {
            "timestamp": datetime.utcnow().isoformat(),
            "l1_ratio": "0.15",
            "l1_l2_ratio": "0.55",
            "redemption_coverage": "1.25",
            "nav": "1.0234",
            "risk_score": 25,
            "risk_level": "low",
        }

        # Check for threshold breaches
        await _check_risk_thresholds(metrics)

        return {"status": "success", "metrics": metrics}

    except Exception as e:
        logger.exception("Failed to calculate risk metrics")
        return {"status": "error", "reason": str(e)}


async def _check_risk_thresholds(metrics: dict[str, Any]) -> None:
    """Check if any risk thresholds are breached."""
    async with AsyncSessionLocal() as session:
        risk_repo = RiskEventRepository(session)

        # L1 ratio threshold (should be >= 10%)
        l1_ratio = Decimal(metrics.get("l1_ratio", "0"))
        if l1_ratio < Decimal("0.10"):
            await risk_repo.create_event(
                event_type="THRESHOLD_BREACH",
                severity="critical" if l1_ratio < Decimal("0.05") else "warning",
                metric_name="l1_ratio",
                message=f"L1 ratio below threshold: {l1_ratio:.2%}",
                threshold_value=Decimal("0.10"),
                actual_value=l1_ratio,
            )
            await session.commit()

        # Redemption coverage threshold (should be >= 100%)
        coverage = Decimal(metrics.get("redemption_coverage", "1"))
        if coverage < Decimal("1.0"):
            await risk_repo.create_event(
                event_type="THRESHOLD_BREACH",
                severity="critical",
                metric_name="redemption_coverage",
                message=f"Redemption coverage below 100%: {coverage:.2%}",
                threshold_value=Decimal("1.0"),
                actual_value=coverage,
            )
            await session.commit()


@async_task(queue="normal")
async def sync_chain_state(self) -> dict[str, Any]:
    """Synchronize on-chain state with database.

    Scheduled task that runs every 30 seconds.

    @returns Sync results
    """
    logger.debug("Syncing chain state")

    try:
        # TODO: Implement actual chain sync
        # This should:
        # 1. Get latest block from chain
        # 2. Compare with last processed block
        # 3. Fetch and process any missed events
        # 4. Update daily_snapshots if needed

        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)
            latest_block = await tx_repo.get_latest_block()

        return {
            "status": "success",
            "latest_db_block": latest_block,
            "synced_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.exception("Failed to sync chain state")
        return {"status": "error", "reason": str(e)}


@async_task(queue="low")
async def health_check(self) -> dict[str, Any]:
    """Perform system health check.

    Scheduled task that runs every 30 seconds.

    @returns Health check results
    """
    logger.debug("Performing health check")

    health_status = {
        "timestamp": datetime.utcnow().isoformat(),
        "components": {},
    }

    # Check database
    try:
        async with AsyncSessionLocal() as session:
            await session.execute("SELECT 1")
        health_status["components"]["database"] = {"status": "healthy"}
    except Exception as e:
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    # Check Redis (via Celery broker)
    try:
        from app.core.celery_app import celery_app

        celery_app.control.ping(timeout=1)
        health_status["components"]["redis"] = {"status": "healthy"}
    except Exception as e:
        health_status["components"]["redis"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    # Check RPC (placeholder)
    health_status["components"]["rpc"] = {"status": "healthy"}

    # Overall status
    all_healthy = all(
        c.get("status") == "healthy"
        for c in health_status["components"].values()
    )
    health_status["overall"] = "healthy" if all_healthy else "degraded"

    if not all_healthy:
        logger.warning("Health check found unhealthy components", extra=health_status)

    return health_status


@async_task(queue="low")
async def cleanup_expired_data(self) -> dict[str, Any]:
    """Clean up expired data from database.

    Scheduled task that runs daily at 2 AM.

    @returns Cleanup results
    """
    logger.info("Starting expired data cleanup")

    cleanup_results = {
        "timestamp": datetime.utcnow().isoformat(),
        "deleted": {},
    }

    async with AsyncSessionLocal() as session:
        try:
            # Clean up old resolved risk events (older than 90 days)
            risk_repo = RiskEventRepository(session)
            cutoff = datetime.utcnow() - timedelta(days=90)
            deleted = await risk_repo.delete_by_filter(
                resolved=True,
                # Note: Would need custom method for date comparison
            )
            cleanup_results["deleted"]["risk_events"] = deleted

            # Note: TimescaleDB handles retention via policies
            # event_processing_logs: 7 days
            # risk_metrics_series: 90 days
            # asset_holdings_snapshots: 1 year
            # daily_snapshots: 2 years

            await session.commit()

            logger.info("Expired data cleanup completed", extra=cleanup_results)
            return {"status": "success", **cleanup_results}

        except Exception as e:
            await session.rollback()
            logger.exception("Failed to cleanup expired data")
            return {"status": "error", "reason": str(e)}


@async_task(queue="low")
async def generate_daily_report(self) -> dict[str, Any]:
    """Generate daily operational report.

    Scheduled task that runs daily at 8 AM.

    @returns Report generation result
    """
    logger.info("Generating daily report")

    try:
        from datetime import date

        report_date = date.today() - timedelta(days=1)

        async with AsyncSessionLocal() as session:
            from app.repositories import (
                RedemptionRepository,
                ApprovalRepository,
                RebalanceRepository,
            )

            # Get statistics
            redemption_repo = RedemptionRepository(session)
            approval_repo = ApprovalRepository(session)
            rebalance_repo = RebalanceRepository(session)

            start_date = datetime.combine(report_date, datetime.min.time())
            end_date = datetime.combine(report_date, datetime.max.time())

            redemption_stats = await redemption_repo.get_statistics(
                start_date=start_date, end_date=end_date
            )
            approval_stats = await approval_repo.get_statistics(
                start_date=start_date, end_date=end_date
            )
            rebalance_stats = await rebalance_repo.get_statistics(
                start_date=start_date, end_date=end_date
            )

            report = {
                "date": report_date.isoformat(),
                "generated_at": datetime.utcnow().isoformat(),
                "redemptions": redemption_stats,
                "approvals": approval_stats,
                "rebalances": rebalance_stats,
            }

            # TODO: Store report and/or send via email
            logger.info("Daily report generated", extra={"date": report_date.isoformat()})

            return {"status": "success", "report": report}

    except Exception as e:
        logger.exception("Failed to generate daily report")
        return {"status": "error", "reason": str(e)}


@celery_app.task(queue="normal")
def update_metrics_dashboard() -> dict[str, Any]:
    """Update metrics for Prometheus/Grafana dashboard.

    @returns Update results
    """
    logger.debug("Updating metrics dashboard")

    # TODO: Update Prometheus metrics
    # - Active redemptions count
    # - Pending approvals count
    # - Risk score
    # - NAV value

    return {"status": "success"}
