"""Tests for risk monitoring service."""

from decimal import Decimal

import pytest

from app.services.risk import (
    ConcentrationRisk,
    LiquidityRisk,
    PriceRisk,
    RedemptionPressure,
    RiskConfig,
    RiskLevel,
    RiskMonitorService,
    RiskType,
)


class TestLiquidityRisk:
    """Tests for liquidity risk assessment."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = RiskMonitorService()

    def test_liquidity_risk_low(self):
        """Test low liquidity risk assessment."""
        result = self.service.assess_liquidity_risk(
            l1_value=Decimal("15000"),
            total_value=Decimal("100000"),
            pending_redemptions=Decimal("3000"),
        )

        assert result.level == RiskLevel.LOW
        assert result.l1_ratio == Decimal("0.15")
        assert result.coverage_ratio == Decimal("5")
        assert result.score <= 30

    def test_liquidity_risk_medium(self):
        """Test medium liquidity risk assessment."""
        result = self.service.assess_liquidity_risk(
            l1_value=Decimal("8000"),
            total_value=Decimal("100000"),
            pending_redemptions=Decimal("3500"),
        )

        assert result.level == RiskLevel.MEDIUM
        assert result.score > 30
        assert result.score < 60

    def test_liquidity_risk_high(self):
        """Test high liquidity risk assessment."""
        result = self.service.assess_liquidity_risk(
            l1_value=Decimal("6000"),
            total_value=Decimal("100000"),
            pending_redemptions=Decimal("5000"),
        )

        assert result.level == RiskLevel.HIGH
        assert result.score >= 55

    def test_liquidity_risk_critical(self):
        """Test critical liquidity risk assessment."""
        result = self.service.assess_liquidity_risk(
            l1_value=Decimal("3000"),
            total_value=Decimal("100000"),
            pending_redemptions=Decimal("4000"),
        )

        assert result.level == RiskLevel.CRITICAL
        assert result.score >= 80

    def test_liquidity_coverage_affects_level(self):
        """Test that coverage ratio affects risk level."""
        # Good L1 ratio but bad coverage
        result = self.service.assess_liquidity_risk(
            l1_value=Decimal("12000"),
            total_value=Decimal("100000"),
            pending_redemptions=Decimal("15000"),  # Coverage < 1
        )

        # Should be high risk due to coverage
        assert result.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]


class TestPriceRisk:
    """Tests for price risk assessment."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = RiskMonitorService()

    def test_price_risk_low(self):
        """Test low price risk assessment."""
        result = self.service.assess_price_risk(
            current_nav=Decimal("1.05"),
            nav_24h_change=Decimal("0.002"),
            nav_7d_volatility=Decimal("0.003"),
        )

        assert result.level == RiskLevel.LOW
        assert result.score <= 30

    def test_price_risk_medium(self):
        """Test medium price risk assessment."""
        result = self.service.assess_price_risk(
            current_nav=Decimal("1.05"),
            nav_24h_change=Decimal("0.008"),
            nav_7d_volatility=Decimal("0.012"),
        )

        assert result.level == RiskLevel.MEDIUM

    def test_price_risk_high(self):
        """Test high price risk assessment."""
        result = self.service.assess_price_risk(
            current_nav=Decimal("1.05"),
            nav_24h_change=Decimal("0.025"),
            nav_7d_volatility=Decimal("0.018"),
        )

        assert result.level == RiskLevel.HIGH

    def test_price_risk_critical(self):
        """Test critical price risk assessment."""
        result = self.service.assess_price_risk(
            current_nav=Decimal("0.95"),
            nav_24h_change=Decimal("-0.06"),
            nav_7d_volatility=Decimal("0.05"),
        )

        assert result.level == RiskLevel.CRITICAL


class TestConcentrationRisk:
    """Tests for concentration risk assessment."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = RiskMonitorService()

    def test_concentration_risk_low(self):
        """Test low concentration risk assessment."""
        allocations = {
            "USDC": Decimal("0.15"),
            "USDT": Decimal("0.15"),
            "DAI": Decimal("0.15"),
            "BUSD": Decimal("0.15"),
            "TUSD": Decimal("0.15"),
            "USDP": Decimal("0.10"),
            "FRAX": Decimal("0.15"),
        }

        result = self.service.assess_concentration_risk(allocations)

        assert result.level == RiskLevel.LOW
        assert result.largest_asset_ratio == Decimal("0.15")
        assert result.asset_count == 7

    def test_concentration_risk_high_single_asset(self):
        """Test high concentration risk from single asset."""
        # Single asset at 45% (>=0.40 high, <0.50 critical)
        # Top3 at 70% (>=0.60 medium, <0.70 high) - keep below top3_high
        allocations = {
            "USDC": Decimal("0.45"),
            "USDT": Decimal("0.15"),
            "DAI": Decimal("0.10"),
            "BUSD": Decimal("0.10"),
            "TUSD": Decimal("0.10"),
            "FRAX": Decimal("0.10"),
        }

        result = self.service.assess_concentration_risk(allocations)

        assert result.level == RiskLevel.HIGH
        assert result.largest_asset_name == "USDC"

    def test_concentration_risk_high_top3(self):
        """Test high concentration risk from top 3."""
        allocations = {
            "USDC": Decimal("0.30"),
            "USDT": Decimal("0.25"),
            "DAI": Decimal("0.25"),
            "BUSD": Decimal("0.10"),
            "TUSD": Decimal("0.10"),
        }

        result = self.service.assess_concentration_risk(allocations)

        assert result.top3_ratio == Decimal("0.80")
        # Top 3 at 80% is critical
        assert result.level == RiskLevel.CRITICAL

    def test_concentration_empty_portfolio(self):
        """Test concentration risk with empty portfolio."""
        result = self.service.assess_concentration_risk({})

        assert result.level == RiskLevel.LOW
        assert result.asset_count == 0

    def test_hhi_calculation(self):
        """Test HHI index calculation."""
        # Equal allocation should have lower HHI
        equal_allocations = {
            "A": Decimal("0.25"),
            "B": Decimal("0.25"),
            "C": Decimal("0.25"),
            "D": Decimal("0.25"),
        }

        # Concentrated allocation should have higher HHI
        concentrated = {
            "A": Decimal("0.70"),
            "B": Decimal("0.20"),
            "C": Decimal("0.10"),
        }

        equal_result = self.service.assess_concentration_risk(equal_allocations)
        concentrated_result = self.service.assess_concentration_risk(concentrated)

        assert concentrated_result.hhi_index > equal_result.hhi_index


class TestRedemptionPressure:
    """Tests for redemption pressure assessment."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = RiskMonitorService()

    def test_redemption_pressure_low(self):
        """Test low redemption pressure."""
        result = self.service.assess_redemption_pressure(
            pending_count=5,
            pending_value=Decimal("3000"),
            total_aum=Decimal("100000"),
        )

        assert result.level == RiskLevel.LOW
        assert result.pending_ratio == Decimal("0.03")

    def test_redemption_pressure_medium(self):
        """Test medium redemption pressure."""
        # 12% pending ratio (>=0.10 medium, <0.15 high)
        result = self.service.assess_redemption_pressure(
            pending_count=15,
            pending_value=Decimal("12000"),
            total_aum=Decimal("100000"),
        )

        assert result.level == RiskLevel.MEDIUM

    def test_redemption_pressure_high(self):
        """Test high redemption pressure."""
        result = self.service.assess_redemption_pressure(
            pending_count=30,
            pending_value=Decimal("17000"),
            total_aum=Decimal("100000"),
        )

        assert result.level == RiskLevel.HIGH

    def test_redemption_pressure_critical(self):
        """Test critical redemption pressure."""
        result = self.service.assess_redemption_pressure(
            pending_count=50,
            pending_value=Decimal("25000"),
            total_aum=Decimal("100000"),
        )

        assert result.level == RiskLevel.CRITICAL


class TestOverallScore:
    """Tests for overall risk score calculation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = RiskMonitorService()

    def test_overall_score_calculation(self):
        """Test overall score calculation."""
        liquidity = LiquidityRisk(
            l1_ratio=Decimal("0.12"),
            l1_value=Decimal("12000"),
            total_value=Decimal("100000"),
            pending_redemptions=Decimal("3000"),
            coverage_ratio=Decimal("4"),
            level=RiskLevel.LOW,
            score=20,
        )
        price = PriceRisk(
            current_nav=Decimal("1.05"),
            nav_24h_change=Decimal("0.002"),
            nav_7d_volatility=Decimal("0.003"),
            nav_30d_volatility=Decimal("0.004"),
            max_drawdown=Decimal("0.01"),
            level=RiskLevel.LOW,
            score=20,
        )
        concentration = ConcentrationRisk(
            largest_asset_ratio=Decimal("0.15"),
            largest_asset_name="USDC",
            top3_ratio=Decimal("0.40"),
            top3_assets=["USDC", "USDT", "DAI"],
            asset_count=7,
            hhi_index=Decimal("1500"),
            level=RiskLevel.LOW,
            score=20,
        )
        redemption = RedemptionPressure(
            pending_count=5,
            pending_value=Decimal("3000"),
            pending_ratio=Decimal("0.03"),
            avg_redemption_size=Decimal("600"),
            largest_pending=Decimal("1000"),
            time_to_settlement=24,
            level=RiskLevel.LOW,
            score=20,
        )

        score = self.service.calculate_overall_score(
            liquidity, price, concentration, redemption
        )

        assert score.overall_score == 20  # All low = 20
        assert score.overall_level == RiskLevel.LOW

    def test_overall_score_weighted(self):
        """Test weighted overall score."""
        # Create mixed risk levels
        liquidity = LiquidityRisk(
            l1_ratio=Decimal("0.05"),
            l1_value=Decimal("5000"),
            total_value=Decimal("100000"),
            pending_redemptions=Decimal("5000"),
            coverage_ratio=Decimal("1"),
            level=RiskLevel.CRITICAL,
            score=95,
        )
        price = PriceRisk(
            current_nav=Decimal("1.05"),
            nav_24h_change=Decimal("0.002"),
            nav_7d_volatility=Decimal("0.003"),
            nav_30d_volatility=Decimal("0.004"),
            max_drawdown=Decimal("0.01"),
            level=RiskLevel.LOW,
            score=20,
        )
        concentration = ConcentrationRisk(
            largest_asset_ratio=Decimal("0.15"),
            largest_asset_name="USDC",
            top3_ratio=Decimal("0.40"),
            top3_assets=["USDC", "USDT", "DAI"],
            asset_count=7,
            hhi_index=Decimal("1500"),
            level=RiskLevel.LOW,
            score=20,
        )
        redemption = RedemptionPressure(
            pending_count=5,
            pending_value=Decimal("3000"),
            pending_ratio=Decimal("0.03"),
            avg_redemption_size=Decimal("600"),
            largest_pending=Decimal("1000"),
            time_to_settlement=24,
            level=RiskLevel.LOW,
            score=20,
        )

        score = self.service.calculate_overall_score(
            liquidity, price, concentration, redemption
        )

        # Critical liquidity (95 * 0.35 = 33.25) should pull score up
        assert score.overall_score > 30


class TestAlerts:
    """Tests for alert generation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = RiskMonitorService()

    def test_generate_alerts_for_high_risk(self):
        """Test alert generation for high risk."""
        liquidity = LiquidityRisk(
            l1_ratio=Decimal("0.05"),
            l1_value=Decimal("5000"),
            total_value=Decimal("100000"),
            pending_redemptions=Decimal("5000"),
            coverage_ratio=Decimal("1"),
            level=RiskLevel.HIGH,
            score=70,
        )
        price = PriceRisk(
            current_nav=Decimal("1.05"),
            nav_24h_change=Decimal("0.002"),
            nav_7d_volatility=Decimal("0.003"),
            nav_30d_volatility=Decimal("0.004"),
            max_drawdown=Decimal("0.01"),
            level=RiskLevel.LOW,
            score=20,
        )
        concentration = ConcentrationRisk(
            largest_asset_ratio=Decimal("0.15"),
            largest_asset_name="USDC",
            top3_ratio=Decimal("0.40"),
            top3_assets=["USDC", "USDT", "DAI"],
            asset_count=7,
            hhi_index=Decimal("1500"),
            level=RiskLevel.LOW,
            score=20,
        )
        redemption = RedemptionPressure(
            pending_count=5,
            pending_value=Decimal("3000"),
            pending_ratio=Decimal("0.03"),
            avg_redemption_size=Decimal("600"),
            largest_pending=Decimal("1000"),
            time_to_settlement=24,
            level=RiskLevel.LOW,
            score=20,
        )

        alerts = self.service.generate_alerts(
            liquidity, price, concentration, redemption
        )

        assert len(alerts) == 1
        assert alerts[0].risk_type == RiskType.LIQUIDITY
        assert alerts[0].level == RiskLevel.HIGH

    def test_no_alerts_for_low_risk(self):
        """Test no alerts for low risk."""
        liquidity = LiquidityRisk(
            l1_ratio=Decimal("0.12"),
            l1_value=Decimal("12000"),
            total_value=Decimal("100000"),
            pending_redemptions=Decimal("3000"),
            coverage_ratio=Decimal("4"),
            level=RiskLevel.LOW,
            score=20,
        )
        price = PriceRisk(
            current_nav=Decimal("1.05"),
            nav_24h_change=Decimal("0.002"),
            nav_7d_volatility=Decimal("0.003"),
            nav_30d_volatility=Decimal("0.004"),
            max_drawdown=Decimal("0.01"),
            level=RiskLevel.LOW,
            score=20,
        )
        concentration = ConcentrationRisk(
            largest_asset_ratio=Decimal("0.15"),
            largest_asset_name="USDC",
            top3_ratio=Decimal("0.40"),
            top3_assets=["USDC", "USDT", "DAI"],
            asset_count=7,
            hhi_index=Decimal("1500"),
            level=RiskLevel.LOW,
            score=20,
        )
        redemption = RedemptionPressure(
            pending_count=5,
            pending_value=Decimal("3000"),
            pending_ratio=Decimal("0.03"),
            avg_redemption_size=Decimal("600"),
            largest_pending=Decimal("1000"),
            time_to_settlement=24,
            level=RiskLevel.LOW,
            score=20,
        )

        alerts = self.service.generate_alerts(
            liquidity, price, concentration, redemption
        )

        assert len(alerts) == 0


class TestCompleteAssessment:
    """Tests for complete risk assessment."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = RiskMonitorService()

    def test_perform_assessment(self):
        """Test complete assessment."""
        assessment = self.service.perform_assessment(
            l1_value=Decimal("12000"),
            total_value=Decimal("100000"),
            pending_redemptions=Decimal("3000"),
            current_nav=Decimal("1.05"),
            nav_24h_change=Decimal("0.002"),
            nav_7d_volatility=Decimal("0.003"),
            asset_allocations={
                "USDC": Decimal("0.15"),
                "USDT": Decimal("0.15"),
                "DAI": Decimal("0.15"),
                "BUSD": Decimal("0.55"),
            },
            pending_count=5,
        )

        assert assessment.assessment_id.startswith("ASM-")
        assert assessment.overall is not None
        assert assessment.liquidity is not None
        assert assessment.price is not None
        assert assessment.concentration is not None
        assert assessment.redemption is not None
        assert len(assessment.recommendations) > 0

    def test_assessment_generates_alerts(self):
        """Test that assessment generates alerts for high risk."""
        assessment = self.service.perform_assessment(
            l1_value=Decimal("3000"),  # Critical liquidity
            total_value=Decimal("100000"),
            pending_redemptions=Decimal("5000"),
            current_nav=Decimal("1.05"),
            nav_24h_change=Decimal("0.002"),
            nav_7d_volatility=Decimal("0.003"),
            asset_allocations={
                "USDC": Decimal("0.50"),  # High concentration
                "USDT": Decimal("0.50"),
            },
            pending_count=5,
        )

        # Should have alerts for liquidity and concentration
        assert len(assessment.alerts) >= 1


class TestAlertManagement:
    """Tests for alert management."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = RiskMonitorService()
        # Create an alert by performing high risk assessment
        self.service.perform_assessment(
            l1_value=Decimal("3000"),
            total_value=Decimal("100000"),
            pending_redemptions=Decimal("5000"),
            current_nav=Decimal("1.05"),
            nav_24h_change=Decimal("0.002"),
            nav_7d_volatility=Decimal("0.003"),
            asset_allocations={"USDC": Decimal("1.0")},
            pending_count=5,
        )

    def test_get_active_alerts(self):
        """Test getting active alerts."""
        alerts = self.service.get_active_alerts()
        assert len(alerts) > 0

    def test_acknowledge_alert(self):
        """Test acknowledging an alert."""
        alerts = self.service.get_active_alerts()
        alert_id = alerts[0].alert_id

        result = self.service.acknowledge_alert(alert_id)
        assert result is True

        alert = self.service.get_alert(alert_id)
        assert alert.acknowledged_at is not None

    def test_resolve_alert(self):
        """Test resolving an alert."""
        alerts = self.service.get_active_alerts()
        alert_id = alerts[0].alert_id

        result = self.service.resolve_alert(alert_id)
        assert result is True

        # Should no longer appear in active alerts
        active = self.service.get_active_alerts()
        assert alert_id not in [a.alert_id for a in active]

    def test_filter_alerts_by_type(self):
        """Test filtering alerts by type."""
        # Get liquidity alerts only
        alerts = self.service.get_active_alerts(risk_type=RiskType.LIQUIDITY)

        for alert in alerts:
            assert alert.risk_type == RiskType.LIQUIDITY


class TestConfigUpdate:
    """Tests for config updates."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = RiskMonitorService()

    def test_update_config(self):
        """Test updating risk configuration."""
        new_config = RiskConfig(
            l1_ratio_critical=Decimal("0.03"),
            l1_ratio_high=Decimal("0.05"),
        )

        self.service.update_config(new_config)

        assert self.service.config.l1_ratio_critical == Decimal("0.03")
        assert self.service.config.l1_ratio_high == Decimal("0.05")
