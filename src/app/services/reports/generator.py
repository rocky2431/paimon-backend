"""Report generation service."""

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.services.reports.schemas import (
    AllocationSummary,
    DailyReport,
    ExportFormat,
    FlowSummary,
    MonthlyReport,
    NavSummary,
    ReportConfig,
    ReportMetadata,
    ReportStatus,
    ReportType,
    RiskSummary,
    StoredReport,
    WeeklyReport,
)

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Service for generating fund reports.

    Features:
    - Daily, weekly, monthly reports
    - Multiple export formats (PDF, Excel, CSV, JSON)
    - Storage integration (S3/MinIO simulation)
    - Report history tracking
    """

    def __init__(self, config: ReportConfig | None = None):
        """Initialize report generator.

        Args:
            config: Report configuration
        """
        self.config = config or ReportConfig()
        self._reports: dict[str, StoredReport] = {}
        self._report_data: dict[str, Any] = {}
        self._storage_base = "/reports"  # Simulated storage path

    def _generate_report_id(self, report_type: ReportType, report_date: date) -> str:
        """Generate unique report ID.

        Args:
            report_type: Type of report
            report_date: Report date

        Returns:
            Report ID
        """
        date_str = report_date.strftime("%Y%m%d")
        return f"RPT-{report_type.value}-{date_str}-{uuid.uuid4().hex[:6].upper()}"

    def _create_metadata(
        self,
        report_id: str,
        report_type: ReportType,
        period_start: date,
        period_end: date,
        format: ExportFormat,
    ) -> ReportMetadata:
        """Create report metadata.

        Args:
            report_id: Report ID
            report_type: Report type
            period_start: Period start
            period_end: Period end
            format: Export format

        Returns:
            Report metadata
        """
        return ReportMetadata(
            report_id=report_id,
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
            generated_at=datetime.now(timezone.utc),
            status=ReportStatus.COMPLETED,
            format=format,
        )

    def generate_daily_report(
        self,
        report_date: date,
        format: ExportFormat = ExportFormat.PDF,
    ) -> DailyReport:
        """Generate daily report.

        Args:
            report_date: Date for report
            format: Export format

        Returns:
            Daily report
        """
        report_id = self._generate_report_id(ReportType.DAILY, report_date)

        # Generate mock data (in production, fetch from services)
        nav_change = Decimal("0.0012")
        opening_nav = Decimal("1.0500")
        closing_nav = opening_nav + nav_change

        aum_change = Decimal("125000")
        opening_aum = Decimal("25000000")
        closing_aum = opening_aum + aum_change

        subscriptions = Decimal("150000")
        redemptions = Decimal("75000")

        # Determine highlights and concerns
        highlights = []
        concerns = []

        if nav_change > 0:
            highlights.append(f"Positive NAV change: +{nav_change:.4f}")
        if subscriptions > redemptions:
            highlights.append(f"Net inflow: {subscriptions - redemptions:,.0f}")

        report = DailyReport(
            metadata=self._create_metadata(
                report_id, ReportType.DAILY, report_date, report_date, format
            ),
            report_date=report_date,
            opening_nav=opening_nav,
            closing_nav=closing_nav,
            nav_change=nav_change,
            nav_change_percent=nav_change / opening_nav * 100,
            opening_aum=opening_aum,
            closing_aum=closing_aum,
            aum_change=aum_change,
            subscriptions=subscriptions,
            redemptions=redemptions,
            net_flow=subscriptions - redemptions,
            subscription_count=12,
            redemption_count=5,
            risk_score=25,
            risk_level="LOW",
            active_alerts=0,
            l1_allocation=Decimal("35.0"),
            l2_allocation=Decimal("40.0"),
            l3_allocation=Decimal("25.0"),
            highlights=highlights,
            concerns=concerns,
        )

        # Store report
        self._store_report(report_id, ReportType.DAILY, report_date, report_date, format, report)

        logger.info(f"Generated daily report: {report_id}")
        return report

    def generate_weekly_report(
        self,
        week_start: date,
        format: ExportFormat = ExportFormat.PDF,
    ) -> WeeklyReport:
        """Generate weekly report.

        Args:
            week_start: Start of week (Monday)
            format: Export format

        Returns:
            Weekly report
        """
        week_end = week_start + timedelta(days=6)
        report_id = self._generate_report_id(ReportType.WEEKLY, week_start)

        # Calculate week number
        week_number = week_start.isocalendar()[1]
        year = week_start.year

        # Generate summaries
        nav_summary = NavSummary(
            start_nav=Decimal("1.0450"),
            end_nav=Decimal("1.0523"),
            high_nav=Decimal("1.0550"),
            low_nav=Decimal("1.0420"),
            change_value=Decimal("0.0073"),
            change_percent=Decimal("0.70"),
            volatility=Decimal("0.15"),
        )

        flow_summary = FlowSummary(
            total_subscriptions=Decimal("1200000"),
            total_redemptions=Decimal("450000"),
            net_flow=Decimal("750000"),
            subscription_count=85,
            redemption_count=32,
            avg_subscription_size=Decimal("14118"),
            avg_redemption_size=Decimal("14063"),
        )

        risk_summary = RiskSummary(
            avg_risk_score=28,
            max_risk_score=42,
            risk_level_distribution={"LOW": 5, "MEDIUM": 2, "HIGH": 0, "CRITICAL": 0},
            alerts_generated=3,
            alerts_resolved=3,
            emergencies_triggered=0,
        )

        allocation_summary = AllocationSummary(
            tier_allocations={"L1": Decimal("35"), "L2": Decimal("40"), "L3": Decimal("25")},
            top_assets=[
                {"name": "USDC", "allocation": Decimal("20")},
                {"name": "vUSDC", "allocation": Decimal("20")},
                {"name": "ibBUSD", "allocation": Decimal("20")},
            ],
            rebalances_executed=1,
            total_rebalance_value=Decimal("500000"),
        )

        # Generate daily summaries
        daily_summaries = []
        for i in range(7):
            day = week_start + timedelta(days=i)
            daily_summaries.append({
                "date": day.isoformat(),
                "nav_change": Decimal(str(0.001 * (i % 3))),
                "net_flow": Decimal(str(100000 * (1 if i % 2 == 0 else -0.5))),
            })

        report = WeeklyReport(
            metadata=self._create_metadata(
                report_id, ReportType.WEEKLY, week_start, week_end, format
            ),
            week_number=week_number,
            year=year,
            nav_summary=nav_summary,
            flow_summary=flow_summary,
            risk_summary=risk_summary,
            allocation_summary=allocation_summary,
            weekly_return=Decimal("0.70"),
            mtd_return=Decimal("1.25"),
            ytd_return=Decimal("5.23"),
            key_events=[
                "Successful rebalancing operation on Tuesday",
                "New institutional investor onboarded",
            ],
            market_commentary="Stable week with moderate inflows",
            outlook="Continued positive outlook with no significant risks",
            daily_summaries=daily_summaries,
        )

        # Store report
        self._store_report(report_id, ReportType.WEEKLY, week_start, week_end, format, report)

        logger.info(f"Generated weekly report: {report_id}")
        return report

    def generate_monthly_report(
        self,
        year: int,
        month: int,
        format: ExportFormat = ExportFormat.PDF,
    ) -> MonthlyReport:
        """Generate monthly comprehensive report.

        Args:
            year: Year
            month: Month
            format: Export format

        Returns:
            Monthly report
        """
        period_start = date(year, month, 1)
        # Calculate last day of month
        if month == 12:
            period_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            period_end = date(year, month + 1, 1) - timedelta(days=1)

        report_id = self._generate_report_id(ReportType.MONTHLY, period_start)

        # Generate summaries
        nav_summary = NavSummary(
            start_nav=Decimal("1.0300"),
            end_nav=Decimal("1.0523"),
            high_nav=Decimal("1.0580"),
            low_nav=Decimal("1.0280"),
            change_value=Decimal("0.0223"),
            change_percent=Decimal("2.17"),
            volatility=Decimal("0.45"),
        )

        flow_summary = FlowSummary(
            total_subscriptions=Decimal("5500000"),
            total_redemptions=Decimal("1800000"),
            net_flow=Decimal("3700000"),
            subscription_count=380,
            redemption_count=125,
            avg_subscription_size=Decimal("14474"),
            avg_redemption_size=Decimal("14400"),
        )

        risk_summary = RiskSummary(
            avg_risk_score=30,
            max_risk_score=55,
            risk_level_distribution={"LOW": 22, "MEDIUM": 7, "HIGH": 1, "CRITICAL": 0},
            alerts_generated=12,
            alerts_resolved=11,
            emergencies_triggered=0,
        )

        allocation_summary = AllocationSummary(
            tier_allocations={"L1": Decimal("35"), "L2": Decimal("40"), "L3": Decimal("25")},
            top_assets=[
                {"name": "USDC", "allocation": Decimal("20")},
                {"name": "vUSDC", "allocation": Decimal("20")},
                {"name": "ibBUSD", "allocation": Decimal("20")},
                {"name": "FIDU", "allocation": Decimal("25")},
            ],
            rebalances_executed=4,
            total_rebalance_value=Decimal("2500000"),
        )

        # Performance attribution
        performance_attribution = {
            "yield_income": Decimal("1.50"),
            "capital_appreciation": Decimal("0.40"),
            "fees": Decimal("-0.08"),
            "other": Decimal("0.35"),
        }

        # Risk metrics
        risk_metrics = {
            "volatility": Decimal("0.45"),
            "sharpe_ratio": Decimal("2.45"),
            "max_drawdown": Decimal("-1.20"),
            "var_95": Decimal("-0.85"),
        }

        # Generate weekly summaries
        weekly_summaries = []
        current = period_start
        week_num = 1
        while current <= period_end:
            weekly_summaries.append({
                "week": week_num,
                "start_date": current.isoformat(),
                "return": Decimal(str(0.5 + week_num * 0.1)),
            })
            current += timedelta(days=7)
            week_num += 1

        report = MonthlyReport(
            metadata=self._create_metadata(
                report_id, ReportType.MONTHLY, period_start, period_end, format
            ),
            month=month,
            year=year,
            nav_summary=nav_summary,
            flow_summary=flow_summary,
            risk_summary=risk_summary,
            allocation_summary=allocation_summary,
            monthly_return=Decimal("2.17"),
            benchmark_return=Decimal("1.50"),
            alpha=Decimal("0.67"),
            sharpe_ratio=Decimal("2.45"),
            max_drawdown=Decimal("-1.20"),
            performance_attribution=performance_attribution,
            risk_metrics=risk_metrics,
            recommendations=[
                "Consider increasing L3 allocation for higher yield",
                "Monitor liquidity during month-end redemption cycle",
            ],
            weekly_summaries=weekly_summaries,
        )

        # Store report
        self._store_report(report_id, ReportType.MONTHLY, period_start, period_end, format, report)

        logger.info(f"Generated monthly report: {report_id}")
        return report

    def _store_report(
        self,
        report_id: str,
        report_type: ReportType,
        period_start: date,
        period_end: date,
        format: ExportFormat,
        report_data: Any,
    ) -> StoredReport:
        """Store report to simulated storage.

        Args:
            report_id: Report ID
            report_type: Report type
            period_start: Period start
            period_end: Period end
            format: Export format
            report_data: Report data

        Returns:
            Stored report reference
        """
        # Simulate file storage
        storage_path = (
            f"{self._storage_base}/{report_type.value.lower()}/"
            f"{period_start.year}/{period_start.month:02d}/"
            f"{report_id}.{format.value.lower()}"
        )

        # Calculate simulated file size
        json_data = report_data.model_dump_json() if hasattr(report_data, "model_dump_json") else "{}"
        file_size = len(json_data.encode())

        stored = StoredReport(
            report_id=report_id,
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
            format=format,
            status=ReportStatus.COMPLETED,
            storage_path=storage_path,
            file_size_bytes=file_size,
            created_at=datetime.now(timezone.utc),
            download_url=f"/api/v1/reports/download/{report_id}",
        )

        self._reports[report_id] = stored
        self._report_data[report_id] = report_data

        return stored

    def get_report(self, report_id: str) -> StoredReport | None:
        """Get stored report by ID.

        Args:
            report_id: Report ID

        Returns:
            Stored report or None
        """
        return self._reports.get(report_id)

    def get_report_data(self, report_id: str) -> Any | None:
        """Get report data by ID.

        Args:
            report_id: Report ID

        Returns:
            Report data or None
        """
        return self._report_data.get(report_id)

    def list_reports(
        self,
        report_type: ReportType | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 50,
    ) -> list[StoredReport]:
        """List stored reports.

        Args:
            report_type: Filter by type
            start_date: Filter by period start
            end_date: Filter by period end
            limit: Max reports

        Returns:
            List of stored reports
        """
        reports = list(self._reports.values())

        if report_type:
            reports = [r for r in reports if r.report_type == report_type]

        if start_date:
            reports = [r for r in reports if r.period_start >= start_date]

        if end_date:
            reports = [r for r in reports if r.period_end <= end_date]

        # Sort by created_at descending
        reports.sort(key=lambda r: r.created_at, reverse=True)

        return reports[:limit]

    def delete_report(self, report_id: str) -> bool:
        """Delete a stored report.

        Args:
            report_id: Report ID

        Returns:
            True if deleted
        """
        if report_id in self._reports:
            del self._reports[report_id]
            self._report_data.pop(report_id, None)
            logger.info(f"Deleted report: {report_id}")
            return True
        return False

    def export_report(
        self,
        report_id: str,
        format: ExportFormat,
    ) -> bytes | None:
        """Export report to specified format.

        Args:
            report_id: Report ID
            format: Target format

        Returns:
            Report bytes or None
        """
        report_data = self._report_data.get(report_id)
        if not report_data:
            return None

        if format == ExportFormat.JSON:
            return report_data.model_dump_json().encode()
        elif format == ExportFormat.CSV:
            # Simplified CSV export
            return self._to_csv(report_data)
        elif format == ExportFormat.PDF:
            # Simplified PDF placeholder
            return b"PDF_PLACEHOLDER_" + report_data.model_dump_json().encode()
        elif format == ExportFormat.EXCEL:
            # Simplified Excel placeholder
            return b"EXCEL_PLACEHOLDER_" + report_data.model_dump_json().encode()

        return None

    def _to_csv(self, report_data: Any) -> bytes:
        """Convert report to CSV.

        Args:
            report_data: Report data

        Returns:
            CSV bytes
        """
        # Simplified CSV generation
        data = report_data.model_dump()
        lines = ["key,value"]

        def flatten(obj, prefix=""):
            items = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    new_key = f"{prefix}.{k}" if prefix else k
                    items.extend(flatten(v, new_key))
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    items.extend(flatten(v, f"{prefix}[{i}]"))
            else:
                items.append((prefix, str(obj)))
            return items

        for key, value in flatten(data):
            lines.append(f'"{key}","{value}"')

        return "\n".join(lines).encode()

    def update_config(self, config: ReportConfig) -> None:
        """Update report configuration.

        Args:
            config: New configuration
        """
        self.config = config
        logger.info("Report configuration updated")


# Singleton instance
_generator: ReportGenerator | None = None


def get_report_generator() -> ReportGenerator:
    """Get or create report generator singleton."""
    global _generator
    if _generator is None:
        _generator = ReportGenerator()
    return _generator
