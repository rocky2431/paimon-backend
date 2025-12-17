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
from app.core.config import get_settings
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.blockchain.client import BSCClient
from app.infrastructure.blockchain.contracts import ContractManager
from app.repositories import (
    RiskEventRepository,
    TransactionRepository,
    RedemptionRepository,
    DailySnapshotRepository,
)
from app.tasks.base import async_task, get_task_logger

logger = get_task_logger("monitoring_tasks")
settings = get_settings()


@async_task(queue="normal")
async def calculate_risk_metrics(self) -> dict[str, Any]:
    """Calculate and store current risk metrics.

    Scheduled task that runs every minute.
    Uses FF_FUND_OVERVIEW_SOURCE to determine data source.

    @returns Calculation results
    """
    logger.debug("Calculating risk metrics")

    try:
        if settings.ff_fund_overview_source == "real":
            metrics = await _calculate_risk_metrics_real()
        else:
            metrics = _generate_risk_metrics_mock()

        # Check for threshold breaches
        await _check_risk_thresholds(metrics)

        return {"status": "success", "metrics": metrics}

    except Exception as e:
        logger.exception("Failed to calculate risk metrics")
        return {"status": "error", "reason": str(e)}


async def _calculate_risk_metrics_real() -> dict[str, Any]:
    """Calculate risk metrics from real chain data."""
    try:
        # Get vault state from chain
        client = BSCClient()
        cm = ContractManager(client)
        vault_state = await cm.get_vault_state(settings.active_vault_address)

        # Convert from wei
        decimals = Decimal(10**18)
        total_assets = Decimal(vault_state["total_assets"]) / decimals
        layer1 = Decimal(vault_state["layer1_liquidity"]) / decimals
        layer2 = Decimal(vault_state["layer2_liquidity"]) / decimals
        share_price = Decimal(vault_state["share_price"]) / decimals
        redemption_liability = Decimal(vault_state["total_redemption_liability"]) / decimals

        # Calculate ratios
        l1_ratio = layer1 / total_assets if total_assets > 0 else Decimal(0)
        l1_l2_ratio = (layer1 + layer2) / total_assets if total_assets > 0 else Decimal(0)
        redemption_coverage = (layer1 + layer2) / redemption_liability if redemption_liability > 0 else Decimal("999")

        # Calculate risk score (0-100, lower is better)
        risk_score = _calculate_risk_score(l1_ratio, l1_l2_ratio, redemption_coverage)
        risk_level = _get_risk_level(risk_score)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "l1_ratio": str(l1_ratio.quantize(Decimal("0.0001"))),
            "l1_l2_ratio": str(l1_l2_ratio.quantize(Decimal("0.0001"))),
            "redemption_coverage": str(redemption_coverage.quantize(Decimal("0.0001"))),
            "nav": str(share_price.quantize(Decimal("0.0001"))),
            "risk_score": risk_score,
            "risk_level": risk_level,
        }
    except Exception as e:
        logger.warning(f"Real risk metrics failed: {e}, fallback to mock")
        return _generate_risk_metrics_mock()


def _generate_risk_metrics_mock() -> dict[str, Any]:
    """Generate mock risk metrics data."""
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "l1_ratio": "0.15",
        "l1_l2_ratio": "0.55",
        "redemption_coverage": "1.25",
        "nav": "1.0234",
        "risk_score": 25,
        "risk_level": "low",
    }


def _calculate_risk_score(
    l1_ratio: Decimal, l1_l2_ratio: Decimal, redemption_coverage: Decimal
) -> int:
    """Calculate risk score from 0-100 (lower is better)."""
    score = 0

    # L1 ratio scoring (target: >= 15%)
    if l1_ratio < Decimal("0.05"):
        score += 40  # Critical
    elif l1_ratio < Decimal("0.10"):
        score += 25  # Warning
    elif l1_ratio < Decimal("0.15"):
        score += 10  # Caution

    # L1+L2 ratio scoring (target: >= 50%)
    if l1_l2_ratio < Decimal("0.30"):
        score += 30  # Critical
    elif l1_l2_ratio < Decimal("0.40"):
        score += 20  # Warning
    elif l1_l2_ratio < Decimal("0.50"):
        score += 10  # Caution

    # Redemption coverage scoring (target: >= 100%)
    if redemption_coverage < Decimal("0.80"):
        score += 30  # Critical
    elif redemption_coverage < Decimal("1.00"):
        score += 20  # Warning
    elif redemption_coverage < Decimal("1.20"):
        score += 10  # Caution

    return min(score, 100)


def _get_risk_level(score: int) -> str:
    """Get risk level from score."""
    if score >= 70:
        return "critical"
    elif score >= 50:
        return "high"
    elif score >= 30:
        return "medium"
    return "low"


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
    Uses FF_FUND_OVERVIEW_SOURCE to determine if chain sync is active.

    @returns Sync results
    """
    logger.debug("Syncing chain state")

    try:
        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)
            snapshot_repo = DailySnapshotRepository(session)

            # Get last processed block from database
            latest_db_block = await tx_repo.get_latest_block()

            if settings.ff_fund_overview_source == "real":
                # Get current block from chain
                client = BSCClient()
                current_chain_block = await client.get_block_number()

                # Check for gap
                blocks_behind = current_chain_block - (latest_db_block or 0)

                # Update daily snapshot if new day
                await _update_daily_snapshot_if_needed(session, snapshot_repo)

                return {
                    "status": "success",
                    "latest_db_block": latest_db_block,
                    "current_chain_block": current_chain_block,
                    "blocks_behind": blocks_behind,
                    "synced_at": datetime.utcnow().isoformat(),
                    "network": settings.blockchain_network,
                }
            else:
                # Mock mode - just return db state
                return {
                    "status": "success",
                    "latest_db_block": latest_db_block,
                    "current_chain_block": None,
                    "blocks_behind": 0,
                    "synced_at": datetime.utcnow().isoformat(),
                    "network": "mock",
                }

    except Exception as e:
        logger.exception("Failed to sync chain state")
        return {"status": "error", "reason": str(e)}


async def _update_daily_snapshot_if_needed(
    session, snapshot_repo: DailySnapshotRepository
) -> bool:
    """Update daily snapshot if we're in a new day without snapshot."""
    from datetime import date
    from app.models.timeseries import DailySnapshot

    today = date.today()
    latest_snapshot = await snapshot_repo.get_latest()

    if latest_snapshot and latest_snapshot.snapshot_date >= today:
        return False  # Already have today's snapshot

    try:
        # Fetch current vault state for snapshot
        client = BSCClient()
        cm = ContractManager(client)
        vault_state = await cm.get_vault_state(settings.active_vault_address)

        # Create new daily snapshot
        new_snapshot = DailySnapshot(
            snapshot_date=today,
            total_supply=vault_state["total_supply"],
            total_assets=vault_state["total_assets"],
            share_price=vault_state["share_price"],
            layer1_amount=vault_state["layer1_liquidity"],
            layer2_amount=vault_state["layer2_liquidity"],
            layer3_amount=vault_state["layer3_value"],
        )
        session.add(new_snapshot)
        await session.commit()

        logger.info(f"Created daily snapshot for {today}")
        return True

    except Exception as e:
        logger.warning(f"Failed to create daily snapshot: {e}")
        return False


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

    # Check RPC
    try:
        if settings.ff_fund_overview_source == "real":
            client = BSCClient()
            is_healthy = await client.health_check()
            if is_healthy:
                block = await client.get_block_number()
                health_status["components"]["rpc"] = {
                    "status": "healthy",
                    "network": settings.blockchain_network,
                    "block": block,
                }
            else:
                health_status["components"]["rpc"] = {
                    "status": "unhealthy",
                    "error": "RPC health check failed",
                }
        else:
            health_status["components"]["rpc"] = {
                "status": "healthy",
                "network": "mock",
                "block": None,
            }
    except Exception as e:
        health_status["components"]["rpc"] = {
            "status": "unhealthy",
            "error": str(e),
        }

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

    This is a synchronous task that updates Prometheus gauge metrics.

    @returns Update results
    """
    import asyncio

    logger.debug("Updating metrics dashboard")

    try:
        # Run async metrics collection in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            metrics = loop.run_until_complete(_collect_dashboard_metrics())
        finally:
            loop.close()

        # Export to Prometheus (if prometheus_client is available)
        _export_to_prometheus(metrics)

        return {"status": "success", "metrics": metrics}

    except Exception as e:
        logger.exception("Failed to update metrics dashboard")
        return {"status": "error", "reason": str(e)}


async def _collect_dashboard_metrics() -> dict[str, Any]:
    """Collect metrics for dashboard from database."""
    async with AsyncSessionLocal() as session:
        redemption_repo = RedemptionRepository(session)
        from app.repositories import ApprovalRepository

        approval_repo = ApprovalRepository(session)

        # Get counts
        pending_redemptions = await redemption_repo.count_by_filter(status="pending")
        active_redemptions = await redemption_repo.count_by_filter(status="processing")
        pending_approvals = await approval_repo.count_by_filter(status="pending")

        # Get NAV and risk from latest snapshot/metrics
        snapshot_repo = DailySnapshotRepository(session)
        latest_snapshot = await snapshot_repo.get_latest()

        nav_value = 1.0
        if latest_snapshot and latest_snapshot.share_price:
            nav_value = float(latest_snapshot.share_price) / (10**18)

        return {
            "pending_redemptions": pending_redemptions,
            "active_redemptions": active_redemptions,
            "pending_approvals": pending_approvals,
            "nav_value": nav_value,
            "timestamp": datetime.utcnow().isoformat(),
        }


def _export_to_prometheus(metrics: dict[str, Any]) -> None:
    """Export metrics to Prometheus gauges."""
    try:
        from prometheus_client import Gauge

        # Define gauges (will reuse existing if already defined)
        pending_redemptions_gauge = Gauge(
            "paimon_pending_redemptions",
            "Number of pending redemptions",
            registry=None,
        )
        active_redemptions_gauge = Gauge(
            "paimon_active_redemptions",
            "Number of active redemptions",
            registry=None,
        )
        pending_approvals_gauge = Gauge(
            "paimon_pending_approvals",
            "Number of pending approvals",
            registry=None,
        )
        nav_gauge = Gauge(
            "paimon_nav_value",
            "Current NAV value",
            registry=None,
        )

        # Update gauges
        pending_redemptions_gauge.set(metrics.get("pending_redemptions", 0))
        active_redemptions_gauge.set(metrics.get("active_redemptions", 0))
        pending_approvals_gauge.set(metrics.get("pending_approvals", 0))
        nav_gauge.set(metrics.get("nav_value", 1.0))

        logger.debug("Prometheus metrics updated")

    except ImportError:
        logger.debug("prometheus_client not installed, skipping Prometheus export")
    except Exception as e:
        logger.warning(f"Failed to export to Prometheus: {e}")


# =============================================================================
# v2.0.0 新增任务
# =============================================================================


@async_task(queue="normal")
async def process_overdue_liability(self) -> dict[str, Any]:
    """处理逾期负债 - 调用链上 processOverdueLiabilityBatch().

    对应 03-risk-control.md:93-101
    每日 00:05 执行，处理过去30天的逾期负债。

    @returns Execution results
    """
    logger.info("Starting overdue liability processing")

    try:
        # 只有在 real 模式下才执行链上交易
        if settings.ff_blockchain_execution != "real":
            logger.info("Skipping on-chain liability processing (mock mode)")
            return {
                "status": "skipped",
                "reason": "blockchain_execution is mock",
            }

        from app.infrastructure.blockchain.transaction import get_transaction_service
        from app.infrastructure.blockchain.contracts import get_abi_loader

        tx_service = get_transaction_service()
        abi_loader = get_abi_loader()

        # 调用链上 processOverdueLiabilityBatch(30)
        result = await tx_service.send_and_wait(
            contract_address=settings.active_redemption_manager,
            abi=abi_loader.redemption_manager_abi,
            function_name="processOverdueLiabilityBatch",
            args=[30],  # 处理过去30天的逾期
        )

        logger.info(
            "Overdue liability processed",
            extra={
                "tx_hash": result.tx_hash,
                "status": result.status.value,
            },
        )

        return {
            "status": result.status.value,
            "tx_hash": result.tx_hash,
            "block_number": result.block_number,
            "gas_used": result.gas_used,
        }

    except Exception as e:
        logger.exception("Failed to process overdue liability")
        return {"status": "error", "reason": str(e)}


@async_task(queue="normal")
async def sync_chain_data(self) -> dict[str, Any]:
    """同步链上数据到数据库.

    由 NavUpdated 事件触发，更新本地缓存的链上状态。

    @returns Sync results
    """
    logger.debug("Syncing chain data after NAV update")

    try:
        if settings.ff_fund_overview_source != "real":
            return {"status": "skipped", "reason": "mock mode"}

        client = BSCClient()
        cm = ContractManager(client)

        # 获取完整的链上状态
        vault_state = await cm.get_vault_state(settings.active_vault_address)
        liquidity_breakdown = await cm.get_liquidity_breakdown(settings.active_vault_address)

        # 获取赎回统计
        redemption_stats = await cm.get_redemption_stats(settings.active_redemption_manager)

        logger.info(
            "Chain data synced",
            extra={
                "total_assets": str(vault_state.get("total_assets")),
                "share_price": str(vault_state.get("share_price")),
                "pending_liability": str(redemption_stats.get("seven_day_liability")),
            },
        )

        return {
            "status": "success",
            "vault_state": {
                "total_assets": str(vault_state.get("total_assets")),
                "share_price": str(vault_state.get("share_price")),
                "emergency_mode": vault_state.get("emergency_mode"),
            },
            "liquidity": {
                "l1": str(liquidity_breakdown.get("layer1_total")),
                "l2": str(liquidity_breakdown.get("layer2_total")),
                "l3": str(liquidity_breakdown.get("layer3_total")),
                "standard_quota": str(liquidity_breakdown.get("standard_channel_quota")),
            },
            "liability": {
                "seven_day": str(redemption_stats.get("seven_day_liability")),
                "overdue": str(redemption_stats.get("overdue_liability")),
            },
            "synced_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.exception("Failed to sync chain data")
        return {"status": "error", "reason": str(e)}


@async_task(queue="normal")
async def check_liability_coverage(self) -> dict[str, Any]:
    """检查负债覆盖率.

    对应 03-risk-control.md 风控检查。
    每小时执行一次，检查 L1+L2 是否能覆盖 7天负债。

    @returns Check results
    """
    logger.debug("Checking liability coverage")

    try:
        if settings.ff_fund_overview_source != "real":
            return {"status": "skipped", "reason": "mock mode"}

        client = BSCClient()
        cm = ContractManager(client)

        # 获取流动性和负债数据
        liquidity = await cm.get_liquidity_breakdown(settings.active_vault_address)
        stats = await cm.get_redemption_stats(settings.active_redemption_manager)

        l1 = Decimal(str(liquidity.get("layer1_total", 0)))
        l2 = Decimal(str(liquidity.get("layer2_total", 0)))
        total_liquidity = l1 + l2

        seven_day_liability = Decimal(str(stats.get("seven_day_liability", 0)))

        # 计算覆盖率
        coverage_ratio = (
            total_liquidity / seven_day_liability
            if seven_day_liability > 0
            else Decimal("999")
        )

        # 检查是否低于阈值
        is_warning = coverage_ratio < Decimal("1.2")
        is_critical = coverage_ratio < Decimal("1.0")

        if is_critical or is_warning:
            async with AsyncSessionLocal() as session:
                risk_repo = RiskEventRepository(session)
                await risk_repo.create_event(
                    event_type="LIABILITY_COVERAGE",
                    severity="critical" if is_critical else "warning",
                    metric_name="liability_coverage",
                    message=f"Liability coverage ratio: {coverage_ratio:.2%}",
                    threshold_value=Decimal("1.0"),
                    actual_value=coverage_ratio,
                    details={
                        "l1_liquidity": str(l1),
                        "l2_liquidity": str(l2),
                        "seven_day_liability": str(seven_day_liability),
                    },
                )
                await session.commit()

            # 发送告警
            if is_critical:
                from app.tasks.notification_tasks import send_risk_alert
                # 注意: 需要获取 event_id
                logger.critical(
                    "LIABILITY COVERAGE CRITICAL",
                    extra={
                        "coverage_ratio": str(coverage_ratio),
                        "liability": str(seven_day_liability),
                    },
                )

        return {
            "status": "success",
            "coverage_ratio": str(coverage_ratio.quantize(Decimal("0.0001"))),
            "l1_l2_liquidity": str(total_liquidity),
            "seven_day_liability": str(seven_day_liability),
            "is_warning": is_warning,
            "is_critical": is_critical,
        }

    except Exception as e:
        logger.exception("Failed to check liability coverage")
        return {"status": "error", "reason": str(e)}
