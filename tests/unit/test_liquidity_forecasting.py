"""Tests for liquidity forecasting service."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services.forecasting import (
    ForecastConfig,
    ForecastHorizon,
    LiquidityForecaster,
    SeasonalityType,
)


class TestForecastConfig:
    """Tests for forecast configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ForecastConfig()

        assert config.daily_lookback_days == 30
        assert config.weekly_lookback_weeks == 12
        assert config.min_confidence == 0.5
        assert config.liquidity_safety_margin == Decimal("1.2")

    def test_custom_config(self):
        """Test custom configuration."""
        config = ForecastConfig(
            daily_lookback_days=60,
            liquidity_safety_margin=Decimal("1.5"),
        )

        assert config.daily_lookback_days == 60
        assert config.liquidity_safety_margin == Decimal("1.5")


class TestHistoricalData:
    """Tests for historical data handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.forecaster = LiquidityForecaster()

    def test_add_single_data_point(self):
        """Test adding single historical data point."""
        self.forecaster.add_historical_data(
            date=date(2024, 1, 15),
            redemption_count=10,
            redemption_value=Decimal("50000"),
        )

        assert len(self.forecaster._historical_data) == 1
        assert self.forecaster._historical_data[0]["value"] == Decimal("50000")

    def test_data_sorted_by_date(self):
        """Test that data is sorted by date."""
        self.forecaster.add_historical_data(
            date=date(2024, 1, 20),
            redemption_count=5,
            redemption_value=Decimal("25000"),
        )
        self.forecaster.add_historical_data(
            date=date(2024, 1, 10),
            redemption_count=10,
            redemption_value=Decimal("50000"),
        )

        assert self.forecaster._historical_data[0]["date"] == date(2024, 1, 10)
        assert self.forecaster._historical_data[1]["date"] == date(2024, 1, 20)

    def test_metadata_stored(self):
        """Test that metadata is stored."""
        self.forecaster.add_historical_data(
            date=date(2024, 1, 15),
            redemption_count=10,
            redemption_value=Decimal("50000"),
            metadata={"source": "test"},
        )

        assert self.forecaster._historical_data[0]["metadata"]["source"] == "test"


class TestPatternAnalysis:
    """Tests for pattern analysis."""

    def setup_method(self):
        """Set up test fixtures with historical data."""
        self.forecaster = LiquidityForecaster()
        self._populate_historical_data()

    def _populate_historical_data(self):
        """Populate with 60 days of historical data."""
        base_date = date(2024, 1, 1)
        for i in range(60):
            current_date = base_date + timedelta(days=i)
            day_of_week = current_date.weekday()

            # Vary value by day of week (higher on Monday, lower on weekends)
            base_value = Decimal("10000")
            if day_of_week == 0:  # Monday
                value = base_value * Decimal("1.5")
            elif day_of_week in [5, 6]:  # Weekend
                value = base_value * Decimal("0.5")
            else:
                value = base_value

            self.forecaster.add_historical_data(
                date=current_date,
                redemption_count=int(value / 1000),
                redemption_value=value,
            )

    def test_daily_pattern_detection(self):
        """Test detection of daily patterns."""
        patterns = self.forecaster.analyze_patterns()

        assert SeasonalityType.DAILY in patterns
        daily_patterns = patterns[SeasonalityType.DAILY]
        assert len(daily_patterns) == 7  # One for each day

        # Monday should have higher average
        monday_pattern = next(
            p for p in daily_patterns if p.period_label == "Monday"
        )
        saturday_pattern = next(
            p for p in daily_patterns if p.period_label == "Saturday"
        )

        assert monday_pattern.avg_value > saturday_pattern.avg_value

    def test_weekly_pattern_detection(self):
        """Test detection of weekly patterns."""
        patterns = self.forecaster.analyze_patterns()

        assert SeasonalityType.WEEKLY in patterns
        weekly_patterns = patterns[SeasonalityType.WEEKLY]
        assert len(weekly_patterns) >= 1

    def test_no_patterns_with_insufficient_data(self):
        """Test no patterns detected with insufficient data."""
        forecaster = LiquidityForecaster()
        forecaster.add_historical_data(
            date=date(2024, 1, 1),
            redemption_count=10,
            redemption_value=Decimal("50000"),
        )

        patterns = forecaster.analyze_patterns()

        # Should have no patterns with only 1 data point
        assert SeasonalityType.DAILY not in patterns


class TestRedemptionPrediction:
    """Tests for redemption prediction."""

    def setup_method(self):
        """Set up test fixtures."""
        self.forecaster = LiquidityForecaster()
        self._populate_data()

    def _populate_data(self):
        """Populate 30 days of data."""
        base_date = date(2024, 1, 1)
        for i in range(30):
            self.forecaster.add_historical_data(
                date=base_date + timedelta(days=i),
                redemption_count=10,
                redemption_value=Decimal("10000"),
            )

    def test_predict_daily(self):
        """Test daily prediction."""
        predictions = self.forecaster.predict_redemptions(
            start_date=date(2024, 2, 1),
            horizon=ForecastHorizon.DAILY,
        )

        assert len(predictions) == 1
        assert predictions[0].target_date == date(2024, 2, 1)
        assert predictions[0].predicted_value > 0

    def test_predict_weekly(self):
        """Test weekly prediction."""
        predictions = self.forecaster.predict_redemptions(
            start_date=date(2024, 2, 1),
            horizon=ForecastHorizon.WEEKLY,
        )

        assert len(predictions) == 7

    def test_predict_monthly(self):
        """Test monthly prediction."""
        predictions = self.forecaster.predict_redemptions(
            start_date=date(2024, 2, 1),
            horizon=ForecastHorizon.MONTHLY,
        )

        assert len(predictions) == 30

    def test_prediction_has_confidence(self):
        """Test prediction includes confidence score."""
        predictions = self.forecaster.predict_redemptions(
            start_date=date(2024, 2, 1),
            horizon=ForecastHorizon.DAILY,
        )

        assert 0 <= predictions[0].confidence <= 1

    def test_prediction_bounds(self):
        """Test prediction has lower and upper bounds."""
        predictions = self.forecaster.predict_redemptions(
            start_date=date(2024, 2, 1),
            horizon=ForecastHorizon.DAILY,
        )

        pred = predictions[0]
        assert pred.lower_bound <= pred.predicted_value <= pred.upper_bound


class TestLiquidityForecast:
    """Tests for liquidity forecasting."""

    def setup_method(self):
        """Set up test fixtures."""
        self.forecaster = LiquidityForecaster()
        self._populate_data()

    def _populate_data(self):
        """Populate historical data."""
        base_date = date(2024, 1, 1)
        for i in range(30):
            self.forecaster.add_historical_data(
                date=base_date + timedelta(days=i),
                redemption_count=10,
                redemption_value=Decimal("10000"),
            )

    def test_forecast_sufficient_liquidity(self):
        """Test forecast with sufficient liquidity."""
        forecast = self.forecaster.forecast_liquidity(
            start_date=date(2024, 2, 1),
            horizon=ForecastHorizon.WEEKLY,
            current_l1_value=Decimal("500000"),
        )

        assert forecast.is_sufficient is True
        assert forecast.liquidity_gap == Decimal(0)

    def test_forecast_insufficient_liquidity(self):
        """Test forecast with insufficient liquidity."""
        forecast = self.forecaster.forecast_liquidity(
            start_date=date(2024, 2, 1),
            horizon=ForecastHorizon.WEEKLY,
            current_l1_value=Decimal("10000"),
        )

        assert forecast.is_sufficient is False
        assert forecast.liquidity_gap > 0

    def test_forecast_includes_predictions(self):
        """Test forecast includes daily predictions."""
        forecast = self.forecaster.forecast_liquidity(
            start_date=date(2024, 2, 1),
            horizon=ForecastHorizon.WEEKLY,
            current_l1_value=Decimal("100000"),
        )

        assert len(forecast.daily_predictions) == 7

    def test_forecast_total_matches_sum(self):
        """Test total predicted matches sum of daily."""
        forecast = self.forecaster.forecast_liquidity(
            start_date=date(2024, 2, 1),
            horizon=ForecastHorizon.WEEKLY,
            current_l1_value=Decimal("100000"),
        )

        daily_sum = sum(p.predicted_value for p in forecast.daily_predictions)
        assert forecast.total_predicted_redemptions == daily_sum


class TestRecommendations:
    """Tests for recommendation generation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.forecaster = LiquidityForecaster()
        self._populate_data()

    def _populate_data(self):
        """Populate historical data."""
        base_date = date(2024, 1, 1)
        for i in range(30):
            self.forecaster.add_historical_data(
                date=base_date + timedelta(days=i),
                redemption_count=10,
                redemption_value=Decimal("10000"),
            )

    def test_recommendations_for_insufficient_liquidity(self):
        """Test recommendations when liquidity is insufficient."""
        forecast = self.forecaster.forecast_liquidity(
            start_date=date(2024, 2, 1),
            horizon=ForecastHorizon.WEEKLY,
            current_l1_value=Decimal("10000"),
        )

        recommendations = self.forecaster.generate_recommendations(forecast)

        # Should have rebalance recommendation
        rebalance_recs = [r for r in recommendations if r.category == "REBALANCE"]
        assert len(rebalance_recs) >= 1

    def test_recommendations_for_healthy_liquidity(self):
        """Test recommendations when liquidity is healthy."""
        forecast = self.forecaster.forecast_liquidity(
            start_date=date(2024, 2, 1),
            horizon=ForecastHorizon.WEEKLY,
            current_l1_value=Decimal("1000000"),
        )

        recommendations = self.forecaster.generate_recommendations(forecast)

        # Should have healthy status
        monitor_recs = [r for r in recommendations if r.category == "MONITOR"]
        assert any("Healthy" in r.title for r in monitor_recs)

    def test_recommendation_has_urgency(self):
        """Test recommendations include urgency hours."""
        forecast = self.forecaster.forecast_liquidity(
            start_date=date(2024, 2, 1),
            horizon=ForecastHorizon.WEEKLY,
            current_l1_value=Decimal("10000"),
        )

        recommendations = self.forecaster.generate_recommendations(forecast)

        for rec in recommendations:
            assert rec.urgency_hours > 0


class TestCompleteForecast:
    """Tests for complete forecast."""

    def setup_method(self):
        """Set up test fixtures."""
        self.forecaster = LiquidityForecaster()
        self._populate_data()

    def _populate_data(self):
        """Populate historical data."""
        base_date = date(2024, 1, 1)
        for i in range(30):
            self.forecaster.add_historical_data(
                date=base_date + timedelta(days=i),
                redemption_count=10,
                redemption_value=Decimal("10000"),
            )

    def test_perform_forecast(self):
        """Test complete forecast."""
        result = self.forecaster.perform_forecast(
            horizon=ForecastHorizon.WEEKLY,
            current_l1_value=Decimal("100000"),
            start_date=date(2024, 2, 1),
        )

        assert result.forecast_id.startswith("FCT-")
        assert result.liquidity_forecast is not None
        assert len(result.recommendations) >= 1

    def test_forecast_stored(self):
        """Test forecast is stored."""
        self.forecaster.perform_forecast(
            horizon=ForecastHorizon.WEEKLY,
            current_l1_value=Decimal("100000"),
        )

        recent = self.forecaster.get_recent_forecasts()
        assert len(recent) >= 1

    def test_forecast_metadata(self):
        """Test forecast includes metadata."""
        result = self.forecaster.perform_forecast(
            horizon=ForecastHorizon.WEEKLY,
            current_l1_value=Decimal("100000"),
        )

        assert "historical_data_points" in result.model_metadata
        assert result.model_metadata["horizon"] == "WEEKLY"


class TestConfigUpdate:
    """Tests for configuration updates."""

    def test_update_config(self):
        """Test updating configuration."""
        forecaster = LiquidityForecaster()
        new_config = ForecastConfig(
            liquidity_safety_margin=Decimal("2.0"),
        )

        forecaster.update_config(new_config)

        assert forecaster.config.liquidity_safety_margin == Decimal("2.0")


class TestForecastHorizons:
    """Tests for different forecast horizons."""

    def setup_method(self):
        """Set up test fixtures."""
        self.forecaster = LiquidityForecaster()
        base_date = date(2024, 1, 1)
        for i in range(90):
            self.forecaster.add_historical_data(
                date=base_date + timedelta(days=i),
                redemption_count=10,
                redemption_value=Decimal("10000"),
            )

    def test_quarterly_forecast(self):
        """Test quarterly (90 day) forecast."""
        result = self.forecaster.perform_forecast(
            horizon=ForecastHorizon.QUARTERLY,
            current_l1_value=Decimal("500000"),
        )

        assert len(result.liquidity_forecast.daily_predictions) == 90

    def test_different_horizons_different_totals(self):
        """Test that different horizons produce different totals."""
        weekly = self.forecaster.perform_forecast(
            horizon=ForecastHorizon.WEEKLY,
            current_l1_value=Decimal("500000"),
        )
        monthly = self.forecaster.perform_forecast(
            horizon=ForecastHorizon.MONTHLY,
            current_l1_value=Decimal("500000"),
        )

        # Monthly should have higher total (more days)
        assert (
            monthly.liquidity_forecast.total_predicted_redemptions
            > weekly.liquidity_forecast.total_predicted_redemptions
        )
