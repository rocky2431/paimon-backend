"""Liquidity forecasting service."""

import logging
import statistics
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.services.forecasting.schemas import (
    ForecastConfig,
    ForecastHorizon,
    ForecastResult,
    LiquidityForecast,
    LiquidityRecommendation,
    RedemptionPattern,
    RedemptionPrediction,
    SeasonalityType,
)

logger = logging.getLogger(__name__)


class LiquidityForecaster:
    """Service for predicting liquidity needs.

    Features:
    - Historical pattern analysis
    - Seasonality detection (daily, weekly, monthly)
    - Redemption prediction
    - Liquidity gap analysis
    - Proactive recommendations
    """

    def __init__(self, config: ForecastConfig | None = None):
        """Initialize forecaster.

        Args:
            config: Forecasting configuration
        """
        self.config = config or ForecastConfig()
        self._historical_data: list[dict[str, Any]] = []
        self._patterns: dict[SeasonalityType, list[RedemptionPattern]] = {}
        self._forecasts: list[ForecastResult] = []

    def add_historical_data(
        self,
        date: date,
        redemption_count: int,
        redemption_value: Decimal,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add historical redemption data.

        Args:
            date: Date of redemptions
            redemption_count: Number of redemptions
            redemption_value: Total redemption value
            metadata: Additional metadata
        """
        self._historical_data.append({
            "date": date,
            "count": redemption_count,
            "value": redemption_value,
            "day_of_week": date.weekday(),
            "day_of_month": date.day,
            "month": date.month,
            "metadata": metadata or {},
        })

        # Sort by date
        self._historical_data.sort(key=lambda x: x["date"])

    def analyze_patterns(self) -> dict[SeasonalityType, list[RedemptionPattern]]:
        """Analyze historical data for patterns.

        Returns:
            Detected patterns by seasonality type
        """
        patterns = {}

        # Daily patterns (day of week)
        daily_patterns = self._analyze_daily_patterns()
        if daily_patterns:
            patterns[SeasonalityType.DAILY] = daily_patterns

        # Weekly patterns (week of month)
        weekly_patterns = self._analyze_weekly_patterns()
        if weekly_patterns:
            patterns[SeasonalityType.WEEKLY] = weekly_patterns

        # Monthly patterns
        monthly_patterns = self._analyze_monthly_patterns()
        if monthly_patterns:
            patterns[SeasonalityType.MONTHLY] = monthly_patterns

        self._patterns = patterns
        return patterns

    def _analyze_daily_patterns(self) -> list[RedemptionPattern]:
        """Analyze day-of-week patterns.

        Returns:
            List of daily patterns
        """
        if len(self._historical_data) < 7:
            return []

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        patterns = []

        for day_idx in range(7):
            day_data = [
                d for d in self._historical_data
                if d["day_of_week"] == day_idx
            ]

            if not day_data:
                continue

            values = [float(d["value"]) for d in day_data]
            counts = [d["count"] for d in day_data]

            avg_value = Decimal(str(statistics.mean(values))) if values else Decimal(0)
            std_dev = Decimal(str(statistics.stdev(values))) if len(values) > 1 else Decimal(0)

            patterns.append(RedemptionPattern(
                period_type=SeasonalityType.DAILY,
                period_label=day_names[day_idx],
                avg_count=statistics.mean(counts) if counts else 0,
                avg_value=avg_value,
                std_dev=std_dev,
                max_value=Decimal(str(max(values))) if values else Decimal(0),
                sample_count=len(day_data),
            ))

        return patterns

    def _analyze_weekly_patterns(self) -> list[RedemptionPattern]:
        """Analyze week-of-month patterns.

        Returns:
            List of weekly patterns
        """
        if len(self._historical_data) < 28:
            return []

        patterns = []

        for week_num in range(1, 5):
            week_data = [
                d for d in self._historical_data
                if (d["day_of_month"] - 1) // 7 + 1 == week_num
            ]

            if not week_data:
                continue

            values = [float(d["value"]) for d in week_data]
            counts = [d["count"] for d in week_data]

            avg_value = Decimal(str(statistics.mean(values))) if values else Decimal(0)
            std_dev = Decimal(str(statistics.stdev(values))) if len(values) > 1 else Decimal(0)

            patterns.append(RedemptionPattern(
                period_type=SeasonalityType.WEEKLY,
                period_label=f"Week {week_num}",
                avg_count=statistics.mean(counts) if counts else 0,
                avg_value=avg_value,
                std_dev=std_dev,
                max_value=Decimal(str(max(values))) if values else Decimal(0),
                sample_count=len(week_data),
            ))

        return patterns

    def _analyze_monthly_patterns(self) -> list[RedemptionPattern]:
        """Analyze month-of-year patterns.

        Returns:
            List of monthly patterns
        """
        if len(self._historical_data) < 60:  # ~2 months minimum
            return []

        month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        patterns = []

        for month_num in range(1, 13):
            month_data = [
                d for d in self._historical_data
                if d["month"] == month_num
            ]

            if not month_data:
                continue

            values = [float(d["value"]) for d in month_data]
            counts = [d["count"] for d in month_data]

            avg_value = Decimal(str(statistics.mean(values))) if values else Decimal(0)
            std_dev = Decimal(str(statistics.stdev(values))) if len(values) > 1 else Decimal(0)

            patterns.append(RedemptionPattern(
                period_type=SeasonalityType.MONTHLY,
                period_label=month_names[month_num - 1],
                avg_count=statistics.mean(counts) if counts else 0,
                avg_value=avg_value,
                std_dev=std_dev,
                max_value=Decimal(str(max(values))) if values else Decimal(0),
                sample_count=len(month_data),
            ))

        return patterns

    def _get_baseline_prediction(self) -> tuple[Decimal, Decimal]:
        """Get baseline prediction from recent data.

        Returns:
            Tuple of (avg_value, std_dev)
        """
        if not self._historical_data:
            return Decimal("10000"), Decimal("5000")  # Default fallback

        recent = self._historical_data[-30:]  # Last 30 days
        values = [float(d["value"]) for d in recent]

        avg = Decimal(str(statistics.mean(values)))
        std = Decimal(str(statistics.stdev(values))) if len(values) > 1 else avg * Decimal("0.3")

        return avg, std

    def predict_redemptions(
        self,
        start_date: date,
        horizon: ForecastHorizon,
    ) -> list[RedemptionPrediction]:
        """Predict future redemptions.

        Args:
            start_date: Start date for predictions
            horizon: Prediction horizon

        Returns:
            List of daily predictions
        """
        # Determine number of days to predict
        days = {
            ForecastHorizon.DAILY: 1,
            ForecastHorizon.WEEKLY: 7,
            ForecastHorizon.MONTHLY: 30,
            ForecastHorizon.QUARTERLY: 90,
        }[horizon]

        # Get baseline
        base_value, base_std = self._get_baseline_prediction()

        # Get patterns if analyzed
        daily_patterns = self._patterns.get(SeasonalityType.DAILY, [])
        weekly_patterns = self._patterns.get(SeasonalityType.WEEKLY, [])

        predictions = []
        for i in range(days):
            target = start_date + timedelta(days=i)
            day_of_week = target.weekday()
            week_of_month = (target.day - 1) // 7 + 1

            # Start with baseline
            predicted_value = base_value
            factors = []

            # Apply daily seasonality
            if daily_patterns:
                day_pattern = next(
                    (p for p in daily_patterns if p.period_label == [
                        "Monday", "Tuesday", "Wednesday", "Thursday",
                        "Friday", "Saturday", "Sunday"
                    ][day_of_week]),
                    None
                )
                if day_pattern:
                    predicted_value = day_pattern.avg_value
                    factors.append(f"Day pattern: {day_pattern.period_label}")

            # Apply weekly seasonality
            if weekly_patterns:
                week_pattern = next(
                    (p for p in weekly_patterns if p.period_label == f"Week {week_of_month}"),
                    None
                )
                if week_pattern and week_pattern.avg_value > 0:
                    # Blend with weekly pattern
                    predicted_value = (predicted_value + week_pattern.avg_value) / 2
                    factors.append(f"Week pattern: {week_pattern.period_label}")

            # Determine if peak period
            is_peak = predicted_value > base_value * Decimal("1.3")
            if is_peak:
                factors.append("Peak period detected")

            # Calculate bounds
            margin = base_std * Decimal("1.5")
            lower = max(Decimal(0), predicted_value - margin)
            upper = predicted_value + margin

            # Confidence based on data availability
            confidence = min(0.95, 0.5 + len(self._historical_data) / 200)

            predictions.append(RedemptionPrediction(
                target_date=target,
                predicted_count=max(1, int(predicted_value / Decimal("5000"))),  # Estimate count
                predicted_value=predicted_value,
                lower_bound=lower,
                upper_bound=upper,
                confidence=confidence,
                is_peak_period=is_peak,
                contributing_factors=factors,
            ))

        return predictions

    def forecast_liquidity(
        self,
        start_date: date,
        horizon: ForecastHorizon,
        current_l1_value: Decimal,
    ) -> LiquidityForecast:
        """Generate liquidity forecast.

        Args:
            start_date: Start date
            horizon: Forecast horizon
            current_l1_value: Current L1 liquidity

        Returns:
            Liquidity forecast
        """
        # Get predictions
        predictions = self.predict_redemptions(start_date, horizon)

        # Calculate totals
        total_predicted = sum(p.predicted_value for p in predictions)
        peak_daily = max(p.predicted_value for p in predictions) if predictions else Decimal(0)

        # Calculate recommended buffer with safety margin
        recommended_buffer = (
            total_predicted * self.config.liquidity_safety_margin
            + peak_daily * self.config.peak_multiplier
        )

        # Calculate gap
        gap = recommended_buffer - current_l1_value
        is_sufficient = gap <= 0

        return LiquidityForecast(
            forecast_date=start_date,
            horizon=horizon,
            total_predicted_redemptions=total_predicted,
            peak_daily_redemption=peak_daily,
            recommended_l1_buffer=recommended_buffer,
            current_l1_value=current_l1_value,
            liquidity_gap=max(Decimal(0), gap),
            is_sufficient=is_sufficient,
            daily_predictions=predictions,
        )

    def generate_recommendations(
        self,
        forecast: LiquidityForecast,
    ) -> list[LiquidityRecommendation]:
        """Generate recommendations based on forecast.

        Args:
            forecast: Liquidity forecast

        Returns:
            List of recommendations
        """
        recommendations = []
        rec_id = 0

        # Insufficient liquidity
        if not forecast.is_sufficient:
            rec_id += 1
            gap_pct = forecast.liquidity_gap / forecast.current_l1_value * 100 if forecast.current_l1_value > 0 else Decimal(100)

            if gap_pct > Decimal("50"):
                priority = "HIGH"
                urgency = 24
            elif gap_pct > Decimal("25"):
                priority = "MEDIUM"
                urgency = 48
            else:
                priority = "LOW"
                urgency = 72

            recommendations.append(LiquidityRecommendation(
                recommendation_id=f"REC-{rec_id:04d}",
                priority=priority,
                category="REBALANCE",
                title="Increase L1 Liquidity",
                description=(
                    f"Forecasted redemptions of {forecast.total_predicted_redemptions:,.0f} "
                    f"exceed current L1 buffer. Gap: {forecast.liquidity_gap:,.0f}"
                ),
                suggested_action=(
                    f"Rebalance {forecast.liquidity_gap:,.0f} from L2/L3 to L1"
                ),
                estimated_impact=forecast.liquidity_gap,
                urgency_hours=urgency,
                auto_executable=priority != "HIGH",
            ))

        # Peak period warning
        peak_days = [p for p in forecast.daily_predictions if p.is_peak_period]
        if peak_days:
            rec_id += 1
            recommendations.append(LiquidityRecommendation(
                recommendation_id=f"REC-{rec_id:04d}",
                priority="MEDIUM",
                category="ALERT",
                title="Peak Redemption Period Ahead",
                description=(
                    f"Detected {len(peak_days)} peak days in forecast period. "
                    f"Peak: {forecast.peak_daily_redemption:,.0f}"
                ),
                suggested_action="Monitor redemption queue closely",
                estimated_impact=forecast.peak_daily_redemption,
                urgency_hours=48,
                auto_executable=False,
            ))

        # Low confidence warning
        low_confidence_days = [
            p for p in forecast.daily_predictions
            if p.confidence < self.config.min_confidence
        ]
        if low_confidence_days:
            rec_id += 1
            recommendations.append(LiquidityRecommendation(
                recommendation_id=f"REC-{rec_id:04d}",
                priority="LOW",
                category="MONITOR",
                title="Low Prediction Confidence",
                description=(
                    f"{len(low_confidence_days)} days have confidence below "
                    f"{self.config.min_confidence:.0%}. More historical data needed."
                ),
                suggested_action="Continue monitoring and collecting data",
                estimated_impact=Decimal(0),
                urgency_hours=168,  # 1 week
                auto_executable=False,
            ))

        # Healthy liquidity
        if forecast.is_sufficient and not recommendations:
            rec_id += 1
            recommendations.append(LiquidityRecommendation(
                recommendation_id=f"REC-{rec_id:04d}",
                priority="LOW",
                category="MONITOR",
                title="Liquidity Healthy",
                description="Current L1 buffer is sufficient for forecasted redemptions",
                suggested_action="Continue standard monitoring",
                estimated_impact=Decimal(0),
                urgency_hours=168,
                auto_executable=False,
            ))

        return recommendations

    def perform_forecast(
        self,
        horizon: ForecastHorizon,
        current_l1_value: Decimal,
        start_date: date | None = None,
    ) -> ForecastResult:
        """Perform complete forecast.

        Args:
            horizon: Forecast horizon
            current_l1_value: Current L1 value
            start_date: Start date (default: today)

        Returns:
            Complete forecast result
        """
        if start_date is None:
            start_date = date.today()

        # Analyze patterns first
        patterns = self.analyze_patterns()

        # Generate forecast
        forecast = self.forecast_liquidity(start_date, horizon, current_l1_value)

        # Generate recommendations
        recommendations = self.generate_recommendations(forecast)

        # Flatten patterns for result
        all_patterns = []
        for pattern_list in patterns.values():
            all_patterns.extend(pattern_list)

        result = ForecastResult(
            forecast_id=f"FCT-{uuid.uuid4().hex[:8].upper()}",
            generated_at=datetime.now(timezone.utc),
            config=self.config,
            detected_patterns=all_patterns,
            liquidity_forecast=forecast,
            recommendations=recommendations,
            model_metadata={
                "historical_data_points": len(self._historical_data),
                "horizon": horizon.value,
                "patterns_detected": len(all_patterns),
            },
        )

        # Store result
        self._forecasts.append(result)
        if len(self._forecasts) > 100:
            self._forecasts = self._forecasts[-100:]

        logger.info(
            f"Forecast generated: id={result.forecast_id}, "
            f"horizon={horizon.value}, gap={forecast.liquidity_gap:,.0f}"
        )

        return result

    def get_recent_forecasts(self, limit: int = 10) -> list[ForecastResult]:
        """Get recent forecasts.

        Args:
            limit: Max forecasts to return

        Returns:
            List of recent forecasts
        """
        return self._forecasts[-limit:][::-1]

    def update_config(self, config: ForecastConfig) -> None:
        """Update forecasting configuration.

        Args:
            config: New configuration
        """
        self.config = config
        logger.info("Forecasting configuration updated")


# Singleton instance
_forecaster: LiquidityForecaster | None = None


def get_liquidity_forecaster() -> LiquidityForecaster:
    """Get or create liquidity forecaster singleton."""
    global _forecaster
    if _forecaster is None:
        _forecaster = LiquidityForecaster()
    return _forecaster
