"""Tests for Risk API endpoints."""

from datetime import date
from decimal import Decimal

import pytest

from app.services.risk import (
    RiskLevel,
    RiskType,
    get_risk_monitor_service,
)
from app.services.forecasting import (
    ForecastHorizon,
    get_liquidity_forecaster,
)


class TestRiskDashboard:
    """Tests for risk dashboard endpoint."""

    def test_get_dashboard_empty(self):
        """Test dashboard with no assessments."""
        from app.api.v1.endpoints.risk import get_risk_dashboard
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_risk_dashboard()
        )

        assert result.overall_level == RiskLevel.LOW
        assert result.overall_score == 20
        assert result.active_alerts_count == 0

    def test_get_dashboard_after_assessment(self):
        """Test dashboard after performing assessment."""
        from app.api.v1.endpoints.risk import (
            get_risk_dashboard,
            perform_risk_assessment,
            RiskAssessmentRequest,
        )
        import asyncio

        # Perform assessment first
        request = RiskAssessmentRequest(
            l1_value=Decimal("12000"),
            total_value=Decimal("100000"),
            pending_redemptions=Decimal("5000"),
            current_nav=Decimal("1.05"),
            nav_24h_change=Decimal("0.002"),
            asset_allocations={
                "USDC": Decimal("0.20"),
                "USDT": Decimal("0.20"),
                "DAI": Decimal("0.20"),
                "BUSD": Decimal("0.20"),
                "TUSD": Decimal("0.20"),
            },
            pending_count=5,
        )

        asyncio.get_event_loop().run_until_complete(
            perform_risk_assessment(request)
        )

        # Check dashboard
        result = asyncio.get_event_loop().run_until_complete(
            get_risk_dashboard()
        )

        assert result.last_assessment_id is not None


class TestRiskAssessment:
    """Tests for risk assessment endpoints."""

    def test_perform_assessment(self):
        """Test performing risk assessment."""
        from app.api.v1.endpoints.risk import (
            perform_risk_assessment,
            RiskAssessmentRequest,
        )
        import asyncio

        request = RiskAssessmentRequest(
            l1_value=Decimal("15000"),
            total_value=Decimal("100000"),
            pending_redemptions=Decimal("5000"),
            current_nav=Decimal("1.05"),
            nav_24h_change=Decimal("0.002"),
            asset_allocations={
                "USDC": Decimal("0.30"),
                "USDT": Decimal("0.30"),
                "DAI": Decimal("0.40"),
            },
            pending_count=3,
        )

        result = asyncio.get_event_loop().run_until_complete(
            perform_risk_assessment(request)
        )

        assert result.assessment_id.startswith("ASM-")
        assert result.overall is not None
        assert result.liquidity is not None

    def test_assessment_generates_alerts_for_high_risk(self):
        """Test that high risk generates alerts."""
        from app.api.v1.endpoints.risk import (
            perform_risk_assessment,
            RiskAssessmentRequest,
        )
        import asyncio

        # Create high-risk scenario
        request = RiskAssessmentRequest(
            l1_value=Decimal("3000"),  # Very low L1
            total_value=Decimal("100000"),
            pending_redemptions=Decimal("20000"),  # High pending
            current_nav=Decimal("1.05"),
            nav_24h_change=Decimal("0.03"),  # High volatility
            asset_allocations={
                "USDC": Decimal("0.60"),  # High concentration
                "USDT": Decimal("0.40"),
            },
            pending_count=20,
        )

        result = asyncio.get_event_loop().run_until_complete(
            perform_risk_assessment(request)
        )

        # Should have alerts
        assert len(result.alerts) > 0

    def test_get_recent_assessments(self):
        """Test getting recent assessments."""
        from app.api.v1.endpoints.risk import get_recent_assessments
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_recent_assessments(limit=5)
        )

        assert isinstance(result, list)


class TestAlertEndpoints:
    """Tests for alert endpoints."""

    def setup_method(self):
        """Set up test fixtures by creating an alert."""
        from app.api.v1.endpoints.risk import (
            perform_risk_assessment,
            RiskAssessmentRequest,
        )
        import asyncio

        # Create high-risk scenario to generate alerts
        request = RiskAssessmentRequest(
            l1_value=Decimal("3000"),
            total_value=Decimal("100000"),
            pending_redemptions=Decimal("30000"),
            current_nav=Decimal("1.05"),
            nav_24h_change=Decimal("0.04"),
            asset_allocations={
                "USDC": Decimal("0.70"),
                "USDT": Decimal("0.30"),
            },
            pending_count=30,
        )

        asyncio.get_event_loop().run_until_complete(
            perform_risk_assessment(request)
        )

    def test_get_active_alerts(self):
        """Test getting active alerts."""
        from app.api.v1.endpoints.risk import get_active_alerts
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_active_alerts(risk_type=None, level=None)
        )

        assert isinstance(result, list)

    def test_filter_alerts_by_type(self):
        """Test filtering alerts by type."""
        from app.api.v1.endpoints.risk import get_active_alerts
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_active_alerts(risk_type=RiskType.LIQUIDITY, level=None)
        )

        for alert in result:
            assert alert.risk_type == RiskType.LIQUIDITY

    def test_acknowledge_alert(self):
        """Test acknowledging an alert."""
        from app.api.v1.endpoints.risk import (
            get_active_alerts,
            acknowledge_alert,
        )
        import asyncio

        # Get an alert
        alerts = asyncio.get_event_loop().run_until_complete(
            get_active_alerts(risk_type=None, level=None)
        )

        if alerts:
            alert_id = alerts[0].alert_id
            result = asyncio.get_event_loop().run_until_complete(
                acknowledge_alert(alert_id)
            )
            assert result["status"] == "acknowledged"

    def test_resolve_alert(self):
        """Test resolving an alert."""
        from app.api.v1.endpoints.risk import (
            get_active_alerts,
            resolve_alert,
        )
        import asyncio

        alerts = asyncio.get_event_loop().run_until_complete(
            get_active_alerts(risk_type=None, level=None)
        )

        if alerts:
            alert_id = alerts[0].alert_id
            result = asyncio.get_event_loop().run_until_complete(
                resolve_alert(alert_id)
            )
            assert result["status"] == "resolved"


class TestForecastEndpoints:
    """Tests for forecasting endpoints."""

    def setup_method(self):
        """Add historical data for forecasting."""
        from datetime import timedelta

        forecaster = get_liquidity_forecaster()
        base_date = date(2024, 1, 1)

        for i in range(30):
            forecaster.add_historical_data(
                date=base_date + timedelta(days=i),
                redemption_count=10,
                redemption_value=Decimal("10000"),
            )

    def test_generate_forecast(self):
        """Test generating forecast."""
        from app.api.v1.endpoints.risk import (
            generate_forecast,
            ForecastRequest,
        )
        import asyncio

        request = ForecastRequest(
            horizon=ForecastHorizon.WEEKLY,
            current_l1_value=Decimal("100000"),
        )

        result = asyncio.get_event_loop().run_until_complete(
            generate_forecast(request)
        )

        assert result.forecast_id.startswith("FCT-")
        assert result.liquidity_forecast is not None

    def test_get_recent_forecasts(self):
        """Test getting recent forecasts."""
        from app.api.v1.endpoints.risk import get_recent_forecasts
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_recent_forecasts(limit=5)
        )

        assert isinstance(result, list)

    def test_add_historical_data(self):
        """Test adding historical data."""
        from app.api.v1.endpoints.risk import (
            add_historical_data,
            HistoricalDataPoint,
        )
        import asyncio

        data = [
            HistoricalDataPoint(
                data_date=date(2024, 3, 1),
                redemption_count=15,
                redemption_value=Decimal("75000"),
            ),
            HistoricalDataPoint(
                data_date=date(2024, 3, 2),
                redemption_count=12,
                redemption_value=Decimal("60000"),
            ),
        ]

        result = asyncio.get_event_loop().run_until_complete(
            add_historical_data(data)
        )

        assert result["status"] == "added"
        assert result["count"] == 2

    def test_get_patterns(self):
        """Test getting detected patterns."""
        from app.api.v1.endpoints.risk import get_detected_patterns
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_detected_patterns()
        )

        assert isinstance(result, dict)


class TestConfigEndpoints:
    """Tests for configuration endpoints."""

    def test_get_risk_config(self):
        """Test getting risk config."""
        from app.api.v1.endpoints.risk import get_risk_config
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_risk_config()
        )

        assert result.l1_ratio_low is not None
        assert result.l1_ratio_critical is not None

    def test_update_risk_config(self):
        """Test updating risk config."""
        from app.api.v1.endpoints.risk import (
            update_risk_config,
            RiskConfigUpdate,
        )
        import asyncio

        update = RiskConfigUpdate(
            l1_ratio_low=Decimal("0.12"),
        )

        result = asyncio.get_event_loop().run_until_complete(
            update_risk_config(update)
        )

        assert result.l1_ratio_low == Decimal("0.12")

    def test_get_forecast_config(self):
        """Test getting forecast config."""
        from app.api.v1.endpoints.risk import get_forecast_config
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_forecast_config()
        )

        assert result.daily_lookback_days is not None


class TestIndicatorEndpoints:
    """Tests for individual indicator endpoints."""

    def test_liquidity_indicator(self):
        """Test liquidity indicator endpoint."""
        from app.api.v1.endpoints.risk import get_liquidity_details
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_liquidity_details(
                l1_value=Decimal("12000"),
                total_value=Decimal("100000"),
                pending_redemptions=Decimal("5000"),
            )
        )

        assert "l1_ratio" in result
        assert "level" in result

    def test_price_indicator(self):
        """Test price indicator endpoint."""
        from app.api.v1.endpoints.risk import get_price_details
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_price_details(
                current_nav=Decimal("1.05"),
                nav_24h_change=Decimal("0.02"),
            )
        )

        assert "current_nav" in result
        assert "level" in result

    def test_concentration_indicator(self):
        """Test concentration indicator endpoint."""
        from app.api.v1.endpoints.risk import get_concentration_details
        import asyncio

        allocations = {
            "USDC": Decimal("0.30"),
            "USDT": Decimal("0.30"),
            "DAI": Decimal("0.40"),
        }

        result = asyncio.get_event_loop().run_until_complete(
            get_concentration_details(allocations)
        )

        assert "largest_asset_ratio" in result
        assert "hhi_index" in result

    def test_redemption_indicator(self):
        """Test redemption indicator endpoint."""
        from app.api.v1.endpoints.risk import get_redemption_details
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_redemption_details(
                pending_count=10,
                pending_value=Decimal("50000"),
                total_aum=Decimal("1000000"),
            )
        )

        assert "pending_ratio" in result
        assert "level" in result


class TestEmergencyEndpoints:
    """Tests for emergency endpoints."""

    def test_get_active_emergencies(self):
        """Test getting active emergencies."""
        from app.api.v1.endpoints.risk import get_active_emergencies
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_active_emergencies()
        )

        assert isinstance(result, list)
