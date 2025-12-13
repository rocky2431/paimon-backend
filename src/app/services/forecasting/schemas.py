"""Schemas for liquidity forecasting."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ForecastHorizon(str, Enum):
    """Forecast time horizon."""

    DAILY = "DAILY"  # Next day
    WEEKLY = "WEEKLY"  # Next 7 days
    MONTHLY = "MONTHLY"  # Next 30 days
    QUARTERLY = "QUARTERLY"  # Next 90 days


class SeasonalityType(str, Enum):
    """Type of seasonality pattern."""

    DAILY = "DAILY"  # Day of week patterns
    WEEKLY = "WEEKLY"  # Week of month patterns
    MONTHLY = "MONTHLY"  # Month of year patterns
    NONE = "NONE"  # No seasonality detected


class ForecastConfig(BaseModel):
    """Configuration for forecasting."""

    # Lookback periods
    daily_lookback_days: int = Field(default=30, description="Days for daily patterns")
    weekly_lookback_weeks: int = Field(default=12, description="Weeks for weekly patterns")
    monthly_lookback_months: int = Field(default=6, description="Months for monthly patterns")

    # Prediction settings
    min_confidence: float = Field(default=0.5, description="Min confidence threshold")
    include_volatility: bool = Field(default=True, description="Include volatility estimate")

    # Safety margins
    liquidity_safety_margin: Decimal = Field(
        default=Decimal("1.2"), description="Safety multiplier for liquidity"
    )
    peak_multiplier: Decimal = Field(
        default=Decimal("1.5"), description="Multiplier for peak periods"
    )


class RedemptionPattern(BaseModel):
    """Historical redemption pattern."""

    period_type: SeasonalityType = Field(..., description="Type of period")
    period_label: str = Field(..., description="Period label (e.g., 'Monday', 'Week 1')")
    avg_count: float = Field(..., description="Average redemption count")
    avg_value: Decimal = Field(..., description="Average redemption value")
    std_dev: Decimal = Field(..., description="Standard deviation")
    max_value: Decimal = Field(..., description="Maximum observed value")
    sample_count: int = Field(..., description="Number of samples")


class RedemptionPrediction(BaseModel):
    """Prediction for future redemptions."""

    target_date: date = Field(..., description="Target date")
    predicted_count: int = Field(..., description="Predicted redemption count")
    predicted_value: Decimal = Field(..., description="Predicted redemption value")
    lower_bound: Decimal = Field(..., description="Lower confidence bound")
    upper_bound: Decimal = Field(..., description="Upper confidence bound")
    confidence: float = Field(..., ge=0, le=1, description="Prediction confidence")
    is_peak_period: bool = Field(default=False, description="Is this a peak period")
    contributing_factors: list[str] = Field(
        default_factory=list, description="Factors contributing to prediction"
    )


class LiquidityForecast(BaseModel):
    """Liquidity needs forecast."""

    forecast_date: date = Field(..., description="Start date of forecast")
    horizon: ForecastHorizon = Field(..., description="Forecast horizon")
    total_predicted_redemptions: Decimal = Field(
        ..., description="Total predicted redemption value"
    )
    peak_daily_redemption: Decimal = Field(
        ..., description="Peak single-day redemption"
    )
    recommended_l1_buffer: Decimal = Field(
        ..., description="Recommended L1 liquidity buffer"
    )
    current_l1_value: Decimal = Field(..., description="Current L1 value")
    liquidity_gap: Decimal = Field(..., description="Gap between needed and available")
    is_sufficient: bool = Field(..., description="Is current liquidity sufficient")
    daily_predictions: list[RedemptionPrediction] = Field(
        ..., description="Day-by-day predictions"
    )


class LiquidityRecommendation(BaseModel):
    """Recommendation for liquidity management."""

    recommendation_id: str = Field(..., description="Recommendation ID")
    priority: str = Field(..., description="Priority (HIGH/MEDIUM/LOW)")
    category: str = Field(..., description="Category (REBALANCE/ALERT/MONITOR)")
    title: str = Field(..., description="Recommendation title")
    description: str = Field(..., description="Detailed description")
    suggested_action: str = Field(..., description="Suggested action to take")
    estimated_impact: Decimal = Field(..., description="Estimated value impact")
    urgency_hours: int = Field(..., description="Hours before action needed")
    auto_executable: bool = Field(
        default=False, description="Can be auto-executed"
    )


class ForecastResult(BaseModel):
    """Complete forecast result."""

    forecast_id: str = Field(..., description="Forecast ID")
    generated_at: datetime = Field(..., description="Generation timestamp")
    config: ForecastConfig = Field(..., description="Config used")
    detected_patterns: list[RedemptionPattern] = Field(
        ..., description="Detected patterns"
    )
    liquidity_forecast: LiquidityForecast = Field(
        ..., description="Liquidity forecast"
    )
    recommendations: list[LiquidityRecommendation] = Field(
        ..., description="Recommendations"
    )
    model_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Model metadata"
    )
