"""Risk monitoring schemas."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskType(str, Enum):
    """Type of risk indicator."""

    LIQUIDITY = "LIQUIDITY"  # L1 coverage
    PRICE = "PRICE"  # NAV volatility
    CONCENTRATION = "CONCENTRATION"  # Asset concentration
    REDEMPTION = "REDEMPTION"  # Redemption pressure
    OPERATIONAL = "OPERATIONAL"  # System issues
    MARKET = "MARKET"  # External market conditions


class RiskLevel(str, Enum):
    """Risk severity level."""

    LOW = "LOW"  # Green - Normal operation
    MEDIUM = "MEDIUM"  # Yellow - Monitor closely
    HIGH = "HIGH"  # Orange - Take action
    CRITICAL = "CRITICAL"  # Red - Immediate action


class RiskConfig(BaseModel):
    """Configuration for risk thresholds."""

    # Liquidity risk thresholds
    l1_ratio_low: Decimal = Field(default=Decimal("0.10"), description="L1 low threshold")
    l1_ratio_medium: Decimal = Field(default=Decimal("0.08"), description="L1 medium threshold")
    l1_ratio_high: Decimal = Field(default=Decimal("0.06"), description="L1 high threshold")
    l1_ratio_critical: Decimal = Field(default=Decimal("0.04"), description="L1 critical threshold")

    # Coverage thresholds (L1 / pending redemptions)
    coverage_low: Decimal = Field(default=Decimal("3.0"), description="Coverage low threshold")
    coverage_medium: Decimal = Field(default=Decimal("2.0"), description="Coverage medium")
    coverage_high: Decimal = Field(default=Decimal("1.5"), description="Coverage high")
    coverage_critical: Decimal = Field(default=Decimal("1.0"), description="Coverage critical")

    # NAV volatility thresholds (daily %)
    nav_vol_low: Decimal = Field(default=Decimal("0.005"), description="NAV volatility low")
    nav_vol_medium: Decimal = Field(default=Decimal("0.01"), description="NAV volatility medium")
    nav_vol_high: Decimal = Field(default=Decimal("0.02"), description="NAV volatility high")
    nav_vol_critical: Decimal = Field(default=Decimal("0.05"), description="NAV volatility critical")

    # Concentration thresholds (single asset %)
    single_asset_low: Decimal = Field(default=Decimal("0.20"), description="Single asset low")
    single_asset_medium: Decimal = Field(default=Decimal("0.30"), description="Single asset medium")
    single_asset_high: Decimal = Field(default=Decimal("0.40"), description="Single asset high")
    single_asset_critical: Decimal = Field(default=Decimal("0.50"), description="Single asset critical")

    # Top 3 concentration thresholds
    top3_low: Decimal = Field(default=Decimal("0.50"), description="Top 3 low")
    top3_medium: Decimal = Field(default=Decimal("0.60"), description="Top 3 medium")
    top3_high: Decimal = Field(default=Decimal("0.70"), description="Top 3 high")
    top3_critical: Decimal = Field(default=Decimal("0.80"), description="Top 3 critical")

    # Redemption pressure thresholds (pending / AUM %)
    redemption_low: Decimal = Field(default=Decimal("0.05"), description="Redemption low")
    redemption_medium: Decimal = Field(default=Decimal("0.10"), description="Redemption medium")
    redemption_high: Decimal = Field(default=Decimal("0.15"), description="Redemption high")
    redemption_critical: Decimal = Field(default=Decimal("0.20"), description="Redemption critical")


class RiskIndicator(BaseModel):
    """Base risk indicator."""

    risk_type: RiskType = Field(..., description="Type of risk")
    level: RiskLevel = Field(..., description="Risk level")
    score: int = Field(..., ge=0, le=100, description="Risk score (0-100)")
    value: Decimal = Field(..., description="Current value")
    threshold: Decimal = Field(..., description="Threshold for current level")
    message: str = Field(..., description="Human readable message")
    details: dict[str, Any] = Field(default_factory=dict, description="Additional details")
    measured_at: datetime = Field(..., description="Measurement timestamp")


class LiquidityRisk(BaseModel):
    """Liquidity risk assessment."""

    l1_ratio: Decimal = Field(..., description="L1 / Total AUM ratio")
    l1_value: Decimal = Field(..., description="L1 tier value")
    total_value: Decimal = Field(..., description="Total portfolio value")
    pending_redemptions: Decimal = Field(..., description="Pending redemption value")
    coverage_ratio: Decimal = Field(..., description="L1 / Pending redemptions")
    level: RiskLevel = Field(..., description="Risk level")
    score: int = Field(..., ge=0, le=100, description="Risk score")


class PriceRisk(BaseModel):
    """Price/NAV risk assessment."""

    current_nav: Decimal = Field(..., description="Current NAV")
    nav_24h_change: Decimal = Field(..., description="24h NAV change %")
    nav_7d_volatility: Decimal = Field(..., description="7-day volatility")
    nav_30d_volatility: Decimal = Field(..., description="30-day volatility")
    max_drawdown: Decimal = Field(..., description="Max drawdown from peak")
    level: RiskLevel = Field(..., description="Risk level")
    score: int = Field(..., ge=0, le=100, description="Risk score")


class ConcentrationRisk(BaseModel):
    """Asset concentration risk assessment."""

    largest_asset_ratio: Decimal = Field(..., description="Largest single asset ratio")
    largest_asset_name: str = Field(..., description="Largest asset name")
    top3_ratio: Decimal = Field(..., description="Top 3 assets combined ratio")
    top3_assets: list[str] = Field(..., description="Top 3 asset names")
    asset_count: int = Field(..., description="Total unique assets")
    hhi_index: Decimal = Field(
        ..., description="Herfindahl-Hirschman Index (0-10000)"
    )
    level: RiskLevel = Field(..., description="Risk level")
    score: int = Field(..., ge=0, le=100, description="Risk score")


class RedemptionPressure(BaseModel):
    """Redemption pressure assessment."""

    pending_count: int = Field(..., description="Pending redemption count")
    pending_value: Decimal = Field(..., description="Pending redemption value")
    pending_ratio: Decimal = Field(..., description="Pending / AUM ratio")
    avg_redemption_size: Decimal = Field(..., description="Average redemption size")
    largest_pending: Decimal = Field(..., description="Largest pending redemption")
    time_to_settlement: int = Field(..., description="Avg hours to settlement")
    level: RiskLevel = Field(..., description="Risk level")
    score: int = Field(..., ge=0, le=100, description="Risk score")


class RiskScore(BaseModel):
    """Overall risk score."""

    overall_score: int = Field(..., ge=0, le=100, description="Overall risk score")
    overall_level: RiskLevel = Field(..., description="Overall risk level")
    liquidity_score: int = Field(..., ge=0, le=100, description="Liquidity risk score")
    price_score: int = Field(..., ge=0, le=100, description="Price risk score")
    concentration_score: int = Field(..., ge=0, le=100, description="Concentration score")
    redemption_score: int = Field(..., ge=0, le=100, description="Redemption score")
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "liquidity": 0.35,
            "price": 0.20,
            "concentration": 0.25,
            "redemption": 0.20,
        },
        description="Score weights",
    )
    calculated_at: datetime = Field(..., description="Calculation timestamp")


class RiskAlert(BaseModel):
    """Risk alert."""

    alert_id: str = Field(..., description="Alert ID")
    risk_type: RiskType = Field(..., description="Risk type")
    level: RiskLevel = Field(..., description="Alert level")
    title: str = Field(..., description="Alert title")
    message: str = Field(..., description="Detailed message")
    value: Decimal = Field(..., description="Current value")
    threshold: Decimal = Field(..., description="Threshold crossed")
    recommendation: str = Field(..., description="Recommended action")
    created_at: datetime = Field(..., description="Alert creation time")
    acknowledged_at: datetime | None = Field(None, description="Acknowledgement time")
    resolved_at: datetime | None = Field(None, description="Resolution time")


class RiskAssessment(BaseModel):
    """Complete risk assessment."""

    assessment_id: str = Field(..., description="Assessment ID")
    overall: RiskScore = Field(..., description="Overall risk score")
    liquidity: LiquidityRisk = Field(..., description="Liquidity risk")
    price: PriceRisk = Field(..., description="Price risk")
    concentration: ConcentrationRisk = Field(..., description="Concentration risk")
    redemption: RedemptionPressure = Field(..., description="Redemption pressure")
    alerts: list[RiskAlert] = Field(default_factory=list, description="Active alerts")
    recommendations: list[str] = Field(
        default_factory=list, description="Recommendations"
    )
    assessed_at: datetime = Field(..., description="Assessment timestamp")
