"""Tests for report generation service."""

from datetime import date
from decimal import Decimal

import pytest

from app.services.reports import (
    DailyReport,
    ExportFormat,
    MonthlyReport,
    ReportConfig,
    ReportGenerator,
    ReportStatus,
    ReportType,
    WeeklyReport,
)


class TestReportConfig:
    """Tests for report configuration."""

    def test_default_config(self):
        """Test default configuration."""
        config = ReportConfig()

        assert config.include_nav_chart is True
        assert config.include_risk_summary is True
        assert config.default_format == ExportFormat.PDF

    def test_custom_config(self):
        """Test custom configuration."""
        config = ReportConfig(
            include_nav_chart=False,
            default_format=ExportFormat.EXCEL,
        )

        assert config.include_nav_chart is False
        assert config.default_format == ExportFormat.EXCEL


class TestDailyReport:
    """Tests for daily report generation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.generator = ReportGenerator()

    def test_generate_daily_report(self):
        """Test generating daily report."""
        report_date = date(2024, 6, 15)

        report = self.generator.generate_daily_report(report_date)

        assert report.metadata.report_type == ReportType.DAILY
        assert report.report_date == report_date
        assert report.metadata.status == ReportStatus.COMPLETED

    def test_daily_report_has_nav(self):
        """Test daily report includes NAV data."""
        report = self.generator.generate_daily_report(date(2024, 6, 15))

        assert report.opening_nav > 0
        assert report.closing_nav > 0
        assert report.nav_change is not None

    def test_daily_report_has_flows(self):
        """Test daily report includes flow data."""
        report = self.generator.generate_daily_report(date(2024, 6, 15))

        assert report.subscriptions >= 0
        assert report.redemptions >= 0
        assert report.net_flow is not None

    def test_daily_report_has_risk(self):
        """Test daily report includes risk data."""
        report = self.generator.generate_daily_report(date(2024, 6, 15))

        assert report.risk_score >= 0
        assert report.risk_level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

    def test_daily_report_has_allocations(self):
        """Test daily report includes allocations."""
        report = self.generator.generate_daily_report(date(2024, 6, 15))

        total = report.l1_allocation + report.l2_allocation + report.l3_allocation
        assert Decimal("99") <= total <= Decimal("101")

    def test_daily_report_stored(self):
        """Test daily report is stored."""
        report = self.generator.generate_daily_report(date(2024, 6, 15))

        stored = self.generator.get_report(report.metadata.report_id)
        assert stored is not None
        assert stored.report_type == ReportType.DAILY


class TestWeeklyReport:
    """Tests for weekly report generation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.generator = ReportGenerator()

    def test_generate_weekly_report(self):
        """Test generating weekly report."""
        week_start = date(2024, 6, 10)  # Monday

        report = self.generator.generate_weekly_report(week_start)

        assert report.metadata.report_type == ReportType.WEEKLY
        assert report.metadata.period_start == week_start

    def test_weekly_report_has_week_number(self):
        """Test weekly report has week number."""
        report = self.generator.generate_weekly_report(date(2024, 6, 10))

        assert report.week_number > 0
        assert report.year == 2024

    def test_weekly_report_has_nav_summary(self):
        """Test weekly report has NAV summary."""
        report = self.generator.generate_weekly_report(date(2024, 6, 10))

        assert report.nav_summary is not None
        assert report.nav_summary.start_nav > 0
        assert report.nav_summary.end_nav > 0

    def test_weekly_report_has_flow_summary(self):
        """Test weekly report has flow summary."""
        report = self.generator.generate_weekly_report(date(2024, 6, 10))

        assert report.flow_summary is not None
        assert report.flow_summary.total_subscriptions >= 0

    def test_weekly_report_has_risk_summary(self):
        """Test weekly report has risk summary."""
        report = self.generator.generate_weekly_report(date(2024, 6, 10))

        assert report.risk_summary is not None
        assert report.risk_summary.avg_risk_score >= 0

    def test_weekly_report_has_daily_summaries(self):
        """Test weekly report includes daily summaries."""
        report = self.generator.generate_weekly_report(date(2024, 6, 10))

        assert len(report.daily_summaries) == 7

    def test_weekly_report_has_commentary(self):
        """Test weekly report has market commentary."""
        report = self.generator.generate_weekly_report(date(2024, 6, 10))

        assert report.market_commentary is not None
        assert report.outlook is not None


class TestMonthlyReport:
    """Tests for monthly report generation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.generator = ReportGenerator()

    def test_generate_monthly_report(self):
        """Test generating monthly report."""
        report = self.generator.generate_monthly_report(2024, 6)

        assert report.metadata.report_type == ReportType.MONTHLY
        assert report.month == 6
        assert report.year == 2024

    def test_monthly_report_period(self):
        """Test monthly report has correct period."""
        report = self.generator.generate_monthly_report(2024, 6)

        assert report.metadata.period_start == date(2024, 6, 1)
        assert report.metadata.period_end == date(2024, 6, 30)

    def test_monthly_report_has_performance(self):
        """Test monthly report has performance metrics."""
        report = self.generator.generate_monthly_report(2024, 6)

        assert report.monthly_return is not None
        assert report.benchmark_return is not None
        assert report.alpha is not None
        assert report.sharpe_ratio is not None

    def test_monthly_report_has_attribution(self):
        """Test monthly report has performance attribution."""
        report = self.generator.generate_monthly_report(2024, 6)

        assert len(report.performance_attribution) > 0
        assert "yield_income" in report.performance_attribution

    def test_monthly_report_has_risk_metrics(self):
        """Test monthly report has risk metrics."""
        report = self.generator.generate_monthly_report(2024, 6)

        assert len(report.risk_metrics) > 0
        assert "volatility" in report.risk_metrics

    def test_monthly_report_has_recommendations(self):
        """Test monthly report has recommendations."""
        report = self.generator.generate_monthly_report(2024, 6)

        assert isinstance(report.recommendations, list)

    def test_monthly_report_has_weekly_summaries(self):
        """Test monthly report includes weekly summaries."""
        report = self.generator.generate_monthly_report(2024, 6)

        assert len(report.weekly_summaries) >= 4


class TestReportStorage:
    """Tests for report storage."""

    def setup_method(self):
        """Set up test fixtures."""
        self.generator = ReportGenerator()

    def test_get_stored_report(self):
        """Test getting stored report."""
        report = self.generator.generate_daily_report(date(2024, 6, 15))

        stored = self.generator.get_report(report.metadata.report_id)

        assert stored is not None
        assert stored.status == ReportStatus.COMPLETED

    def test_get_report_data(self):
        """Test getting report data."""
        report = self.generator.generate_daily_report(date(2024, 6, 15))

        data = self.generator.get_report_data(report.metadata.report_id)

        assert data is not None
        assert isinstance(data, DailyReport)

    def test_list_reports(self):
        """Test listing reports."""
        self.generator.generate_daily_report(date(2024, 6, 15))
        self.generator.generate_daily_report(date(2024, 6, 16))

        reports = self.generator.list_reports()

        assert len(reports) >= 2

    def test_list_reports_by_type(self):
        """Test listing reports by type."""
        self.generator.generate_daily_report(date(2024, 6, 15))
        self.generator.generate_weekly_report(date(2024, 6, 10))

        daily_reports = self.generator.list_reports(report_type=ReportType.DAILY)
        weekly_reports = self.generator.list_reports(report_type=ReportType.WEEKLY)

        for r in daily_reports:
            assert r.report_type == ReportType.DAILY
        for r in weekly_reports:
            assert r.report_type == ReportType.WEEKLY

    def test_delete_report(self):
        """Test deleting report."""
        report = self.generator.generate_daily_report(date(2024, 6, 15))
        report_id = report.metadata.report_id

        result = self.generator.delete_report(report_id)

        assert result is True
        assert self.generator.get_report(report_id) is None

    def test_delete_nonexistent_report(self):
        """Test deleting nonexistent report."""
        result = self.generator.delete_report("NONEXISTENT")

        assert result is False


class TestReportExport:
    """Tests for report export."""

    def setup_method(self):
        """Set up test fixtures."""
        self.generator = ReportGenerator()

    def test_export_json(self):
        """Test exporting report as JSON."""
        report = self.generator.generate_daily_report(date(2024, 6, 15))

        data = self.generator.export_report(
            report.metadata.report_id,
            ExportFormat.JSON,
        )

        assert data is not None
        assert len(data) > 0

    def test_export_csv(self):
        """Test exporting report as CSV."""
        report = self.generator.generate_daily_report(date(2024, 6, 15))

        data = self.generator.export_report(
            report.metadata.report_id,
            ExportFormat.CSV,
        )

        assert data is not None
        assert b"key,value" in data

    def test_export_pdf(self):
        """Test exporting report as PDF (placeholder)."""
        report = self.generator.generate_daily_report(date(2024, 6, 15))

        data = self.generator.export_report(
            report.metadata.report_id,
            ExportFormat.PDF,
        )

        assert data is not None
        assert b"PDF_PLACEHOLDER_" in data

    def test_export_excel(self):
        """Test exporting report as Excel (placeholder)."""
        report = self.generator.generate_daily_report(date(2024, 6, 15))

        data = self.generator.export_report(
            report.metadata.report_id,
            ExportFormat.EXCEL,
        )

        assert data is not None
        assert b"EXCEL_PLACEHOLDER_" in data

    def test_export_nonexistent(self):
        """Test exporting nonexistent report."""
        data = self.generator.export_report("NONEXISTENT", ExportFormat.JSON)

        assert data is None


class TestReportFormats:
    """Tests for different report formats."""

    def setup_method(self):
        """Set up test fixtures."""
        self.generator = ReportGenerator()

    def test_daily_pdf_format(self):
        """Test daily report with PDF format."""
        report = self.generator.generate_daily_report(
            date(2024, 6, 15),
            format=ExportFormat.PDF,
        )

        assert report.metadata.format == ExportFormat.PDF

    def test_weekly_excel_format(self):
        """Test weekly report with Excel format."""
        report = self.generator.generate_weekly_report(
            date(2024, 6, 10),
            format=ExportFormat.EXCEL,
        )

        assert report.metadata.format == ExportFormat.EXCEL

    def test_monthly_json_format(self):
        """Test monthly report with JSON format."""
        report = self.generator.generate_monthly_report(
            2024, 6,
            format=ExportFormat.JSON,
        )

        assert report.metadata.format == ExportFormat.JSON


class TestConfigUpdate:
    """Tests for configuration updates."""

    def test_update_config(self):
        """Test updating configuration."""
        generator = ReportGenerator()
        new_config = ReportConfig(
            include_nav_chart=False,
            default_format=ExportFormat.CSV,
        )

        generator.update_config(new_config)

        assert generator.config.include_nav_chart is False
        assert generator.config.default_format == ExportFormat.CSV
