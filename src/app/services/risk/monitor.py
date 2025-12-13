"""Risk monitoring service."""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.services.risk.schemas import (
    ConcentrationRisk,
    LiquidityRisk,
    PriceRisk,
    RedemptionPressure,
    RiskAlert,
    RiskAssessment,
    RiskConfig,
    RiskIndicator,
    RiskLevel,
    RiskScore,
    RiskType,
)

logger = logging.getLogger(__name__)


class RiskMonitorService:
    """Service for monitoring portfolio risk.

    Features:
    - Liquidity risk monitoring (L1 ratio, coverage)
    - Price risk monitoring (NAV volatility)
    - Concentration risk monitoring (single/top3 assets)
    - Redemption pressure tracking
    - Overall risk scoring
    - Alert generation
    """

    def __init__(self, config: RiskConfig | None = None):
        """Initialize risk monitor service.

        Args:
            config: Risk configuration
        """
        self.config = config or RiskConfig()
        self._alerts: dict[str, RiskAlert] = {}
        self._alert_id = 0
        self._assessments: list[RiskAssessment] = []

    def _get_level(
        self,
        value: Decimal,
        low: Decimal,
        medium: Decimal,
        high: Decimal,
        critical: Decimal,
        higher_is_worse: bool = False,
    ) -> RiskLevel:
        """Determine risk level based on thresholds.

        Args:
            value: Current value
            low: Low threshold
            medium: Medium threshold
            high: High threshold
            critical: Critical threshold
            higher_is_worse: If True, higher values mean higher risk

        Returns:
            Risk level
        """
        if higher_is_worse:
            if value >= critical:
                return RiskLevel.CRITICAL
            elif value >= high:
                return RiskLevel.HIGH
            elif value >= medium:
                return RiskLevel.MEDIUM
            return RiskLevel.LOW
        else:
            if value <= critical:
                return RiskLevel.CRITICAL
            elif value <= high:
                return RiskLevel.HIGH
            elif value <= medium:
                return RiskLevel.MEDIUM
            return RiskLevel.LOW

    def _level_to_score(self, level: RiskLevel) -> int:
        """Convert risk level to score (higher = more risk).

        Args:
            level: Risk level

        Returns:
            Score 0-100
        """
        return {
            RiskLevel.LOW: 20,
            RiskLevel.MEDIUM: 45,
            RiskLevel.HIGH: 70,
            RiskLevel.CRITICAL: 95,
        }[level]

    def _score_to_level(self, score: int) -> RiskLevel:
        """Convert score to risk level.

        Args:
            score: Risk score 0-100

        Returns:
            Risk level
        """
        if score >= 80:
            return RiskLevel.CRITICAL
        elif score >= 55:
            return RiskLevel.HIGH
        elif score >= 30:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def assess_liquidity_risk(
        self,
        l1_value: Decimal,
        total_value: Decimal,
        pending_redemptions: Decimal = Decimal(0),
    ) -> LiquidityRisk:
        """Assess liquidity risk.

        Args:
            l1_value: L1 tier value
            total_value: Total portfolio value
            pending_redemptions: Pending redemption value

        Returns:
            Liquidity risk assessment
        """
        l1_ratio = l1_value / total_value if total_value > 0 else Decimal(0)
        coverage_ratio = (
            l1_value / pending_redemptions
            if pending_redemptions > 0
            else Decimal("999")
        )

        # Assess L1 ratio level
        l1_level = self._get_level(
            l1_ratio,
            self.config.l1_ratio_low,
            self.config.l1_ratio_medium,
            self.config.l1_ratio_high,
            self.config.l1_ratio_critical,
            higher_is_worse=False,
        )

        # Assess coverage level
        coverage_level = self._get_level(
            coverage_ratio,
            self.config.coverage_low,
            self.config.coverage_medium,
            self.config.coverage_high,
            self.config.coverage_critical,
            higher_is_worse=False,
        )

        # Take the worse of the two
        if self._level_to_score(coverage_level) > self._level_to_score(l1_level):
            level = coverage_level
        else:
            level = l1_level

        return LiquidityRisk(
            l1_ratio=l1_ratio,
            l1_value=l1_value,
            total_value=total_value,
            pending_redemptions=pending_redemptions,
            coverage_ratio=coverage_ratio,
            level=level,
            score=self._level_to_score(level),
        )

    def assess_price_risk(
        self,
        current_nav: Decimal,
        nav_24h_change: Decimal,
        nav_7d_volatility: Decimal = Decimal(0),
        nav_30d_volatility: Decimal = Decimal(0),
        max_drawdown: Decimal = Decimal(0),
    ) -> PriceRisk:
        """Assess price/NAV risk.

        Args:
            current_nav: Current NAV
            nav_24h_change: 24h NAV change (absolute %)
            nav_7d_volatility: 7-day volatility
            nav_30d_volatility: 30-day volatility
            max_drawdown: Max drawdown from peak

        Returns:
            Price risk assessment
        """
        # Use the higher of 24h change or 7d volatility
        primary_metric = max(abs(nav_24h_change), nav_7d_volatility)

        level = self._get_level(
            primary_metric,
            self.config.nav_vol_low,
            self.config.nav_vol_medium,
            self.config.nav_vol_high,
            self.config.nav_vol_critical,
            higher_is_worse=True,
        )

        return PriceRisk(
            current_nav=current_nav,
            nav_24h_change=nav_24h_change,
            nav_7d_volatility=nav_7d_volatility,
            nav_30d_volatility=nav_30d_volatility,
            max_drawdown=max_drawdown,
            level=level,
            score=self._level_to_score(level),
        )

    def assess_concentration_risk(
        self,
        asset_allocations: dict[str, Decimal],
    ) -> ConcentrationRisk:
        """Assess concentration risk.

        Args:
            asset_allocations: Asset name -> allocation ratio

        Returns:
            Concentration risk assessment
        """
        if not asset_allocations:
            return ConcentrationRisk(
                largest_asset_ratio=Decimal(0),
                largest_asset_name="",
                top3_ratio=Decimal(0),
                top3_assets=[],
                asset_count=0,
                hhi_index=Decimal(0),
                level=RiskLevel.LOW,
                score=20,
            )

        # Sort by allocation
        sorted_assets = sorted(
            asset_allocations.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        largest_name, largest_ratio = sorted_assets[0]
        top3 = sorted_assets[:3]
        top3_ratio = sum(alloc for _, alloc in top3)
        top3_names = [name for name, _ in top3]

        # Calculate HHI (Herfindahl-Hirschman Index)
        hhi = sum((ratio * 100) ** 2 for ratio in asset_allocations.values())

        # Assess single asset concentration
        single_level = self._get_level(
            largest_ratio,
            self.config.single_asset_low,
            self.config.single_asset_medium,
            self.config.single_asset_high,
            self.config.single_asset_critical,
            higher_is_worse=True,
        )

        # Assess top 3 concentration
        top3_level = self._get_level(
            top3_ratio,
            self.config.top3_low,
            self.config.top3_medium,
            self.config.top3_high,
            self.config.top3_critical,
            higher_is_worse=True,
        )

        # Take the worse of the two
        if self._level_to_score(top3_level) > self._level_to_score(single_level):
            level = top3_level
        else:
            level = single_level

        return ConcentrationRisk(
            largest_asset_ratio=largest_ratio,
            largest_asset_name=largest_name,
            top3_ratio=top3_ratio,
            top3_assets=top3_names,
            asset_count=len(asset_allocations),
            hhi_index=hhi,
            level=level,
            score=self._level_to_score(level),
        )

    def assess_redemption_pressure(
        self,
        pending_count: int,
        pending_value: Decimal,
        total_aum: Decimal,
        avg_redemption_size: Decimal = Decimal(0),
        largest_pending: Decimal = Decimal(0),
        avg_time_to_settlement: int = 24,
    ) -> RedemptionPressure:
        """Assess redemption pressure.

        Args:
            pending_count: Number of pending redemptions
            pending_value: Total pending value
            total_aum: Total AUM
            avg_redemption_size: Average redemption size
            largest_pending: Largest pending redemption
            avg_time_to_settlement: Average hours to settlement

        Returns:
            Redemption pressure assessment
        """
        pending_ratio = pending_value / total_aum if total_aum > 0 else Decimal(0)

        level = self._get_level(
            pending_ratio,
            self.config.redemption_low,
            self.config.redemption_medium,
            self.config.redemption_high,
            self.config.redemption_critical,
            higher_is_worse=True,
        )

        return RedemptionPressure(
            pending_count=pending_count,
            pending_value=pending_value,
            pending_ratio=pending_ratio,
            avg_redemption_size=avg_redemption_size,
            largest_pending=largest_pending,
            time_to_settlement=avg_time_to_settlement,
            level=level,
            score=self._level_to_score(level),
        )

    def calculate_overall_score(
        self,
        liquidity: LiquidityRisk,
        price: PriceRisk,
        concentration: ConcentrationRisk,
        redemption: RedemptionPressure,
        weights: dict[str, float] | None = None,
    ) -> RiskScore:
        """Calculate overall risk score.

        Args:
            liquidity: Liquidity risk
            price: Price risk
            concentration: Concentration risk
            redemption: Redemption pressure
            weights: Custom weights for scoring

        Returns:
            Overall risk score
        """
        if weights is None:
            weights = {
                "liquidity": 0.35,
                "price": 0.20,
                "concentration": 0.25,
                "redemption": 0.20,
            }

        overall_score = int(
            liquidity.score * weights["liquidity"]
            + price.score * weights["price"]
            + concentration.score * weights["concentration"]
            + redemption.score * weights["redemption"]
        )

        return RiskScore(
            overall_score=overall_score,
            overall_level=self._score_to_level(overall_score),
            liquidity_score=liquidity.score,
            price_score=price.score,
            concentration_score=concentration.score,
            redemption_score=redemption.score,
            weights=weights,
            calculated_at=datetime.now(timezone.utc),
        )

    def _create_alert(
        self,
        risk_type: RiskType,
        level: RiskLevel,
        title: str,
        message: str,
        value: Decimal,
        threshold: Decimal,
        recommendation: str,
    ) -> RiskAlert:
        """Create a risk alert.

        Args:
            risk_type: Type of risk
            level: Alert level
            title: Alert title
            message: Detailed message
            value: Current value
            threshold: Threshold crossed
            recommendation: Recommended action

        Returns:
            Risk alert
        """
        self._alert_id += 1
        alert_id = f"ALR-{self._alert_id:08d}"

        alert = RiskAlert(
            alert_id=alert_id,
            risk_type=risk_type,
            level=level,
            title=title,
            message=message,
            value=value,
            threshold=threshold,
            recommendation=recommendation,
            created_at=datetime.now(timezone.utc),
        )

        self._alerts[alert_id] = alert
        return alert

    def generate_alerts(
        self,
        liquidity: LiquidityRisk,
        price: PriceRisk,
        concentration: ConcentrationRisk,
        redemption: RedemptionPressure,
    ) -> list[RiskAlert]:
        """Generate alerts for high/critical risks.

        Args:
            liquidity: Liquidity risk
            price: Price risk
            concentration: Concentration risk
            redemption: Redemption pressure

        Returns:
            List of generated alerts
        """
        alerts = []

        # Liquidity alerts
        if liquidity.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            alerts.append(
                self._create_alert(
                    risk_type=RiskType.LIQUIDITY,
                    level=liquidity.level,
                    title=f"Liquidity Risk: {liquidity.level.value}",
                    message=f"L1 ratio at {liquidity.l1_ratio:.2%}, coverage ratio at {liquidity.coverage_ratio:.1f}x",
                    value=liquidity.l1_ratio,
                    threshold=self.config.l1_ratio_high,
                    recommendation="Consider rebalancing to increase L1 liquidity",
                )
            )

        # Price alerts
        if price.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            alerts.append(
                self._create_alert(
                    risk_type=RiskType.PRICE,
                    level=price.level,
                    title=f"Price Volatility: {price.level.value}",
                    message=f"NAV 24h change: {price.nav_24h_change:.2%}, 7d volatility: {price.nav_7d_volatility:.2%}",
                    value=abs(price.nav_24h_change),
                    threshold=self.config.nav_vol_high,
                    recommendation="Monitor closely, consider hedging strategies",
                )
            )

        # Concentration alerts
        if concentration.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            alerts.append(
                self._create_alert(
                    risk_type=RiskType.CONCENTRATION,
                    level=concentration.level,
                    title=f"Concentration Risk: {concentration.level.value}",
                    message=f"Largest asset ({concentration.largest_asset_name}): {concentration.largest_asset_ratio:.1%}, Top 3: {concentration.top3_ratio:.1%}",
                    value=concentration.largest_asset_ratio,
                    threshold=self.config.single_asset_high,
                    recommendation="Consider diversifying into additional assets",
                )
            )

        # Redemption alerts
        if redemption.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            alerts.append(
                self._create_alert(
                    risk_type=RiskType.REDEMPTION,
                    level=redemption.level,
                    title=f"Redemption Pressure: {redemption.level.value}",
                    message=f"Pending redemptions: {redemption.pending_ratio:.1%} of AUM ({redemption.pending_count} requests)",
                    value=redemption.pending_ratio,
                    threshold=self.config.redemption_high,
                    recommendation="Ensure sufficient liquidity for settlements",
                )
            )

        return alerts

    def perform_assessment(
        self,
        l1_value: Decimal,
        total_value: Decimal,
        pending_redemptions: Decimal,
        current_nav: Decimal,
        nav_24h_change: Decimal,
        nav_7d_volatility: Decimal,
        asset_allocations: dict[str, Decimal],
        pending_count: int,
    ) -> RiskAssessment:
        """Perform complete risk assessment.

        Args:
            l1_value: L1 tier value
            total_value: Total portfolio value
            pending_redemptions: Pending redemption value
            current_nav: Current NAV
            nav_24h_change: 24h NAV change
            nav_7d_volatility: 7-day volatility
            asset_allocations: Asset allocations
            pending_count: Pending redemption count

        Returns:
            Complete risk assessment
        """
        # Assess individual risks
        liquidity = self.assess_liquidity_risk(
            l1_value, total_value, pending_redemptions
        )
        price = self.assess_price_risk(
            current_nav, nav_24h_change, nav_7d_volatility
        )
        concentration = self.assess_concentration_risk(asset_allocations)
        redemption = self.assess_redemption_pressure(
            pending_count, pending_redemptions, total_value
        )

        # Calculate overall score
        overall = self.calculate_overall_score(
            liquidity, price, concentration, redemption
        )

        # Generate alerts
        alerts = self.generate_alerts(liquidity, price, concentration, redemption)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            liquidity, price, concentration, redemption
        )

        assessment = RiskAssessment(
            assessment_id=f"ASM-{uuid.uuid4().hex[:8].upper()}",
            overall=overall,
            liquidity=liquidity,
            price=price,
            concentration=concentration,
            redemption=redemption,
            alerts=alerts,
            recommendations=recommendations,
            assessed_at=datetime.now(timezone.utc),
        )

        # Store assessment
        self._assessments.append(assessment)
        if len(self._assessments) > 1000:
            self._assessments = self._assessments[-1000:]

        logger.info(
            f"Risk assessment completed: overall={overall.overall_level.value}, "
            f"score={overall.overall_score}, alerts={len(alerts)}"
        )

        return assessment

    def _generate_recommendations(
        self,
        liquidity: LiquidityRisk,
        price: PriceRisk,
        concentration: ConcentrationRisk,
        redemption: RedemptionPressure,
    ) -> list[str]:
        """Generate recommendations based on risk assessment.

        Args:
            liquidity: Liquidity risk
            price: Price risk
            concentration: Concentration risk
            redemption: Redemption pressure

        Returns:
            List of recommendations
        """
        recommendations = []

        if liquidity.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            recommendations.append(
                "Initiate rebalancing to increase L1 liquidity buffer"
            )
            if liquidity.coverage_ratio < Decimal("2.0"):
                recommendations.append(
                    "Consider temporary pause on large redemptions"
                )

        if price.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            recommendations.append(
                "Increase monitoring frequency for NAV changes"
            )
            if abs(price.nav_24h_change) > Decimal("0.03"):
                recommendations.append(
                    "Review underlying asset price movements"
                )

        if concentration.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            recommendations.append(
                f"Reduce exposure to {concentration.largest_asset_name}"
            )
            if concentration.asset_count < 5:
                recommendations.append(
                    "Increase diversification with additional assets"
                )

        if redemption.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            recommendations.append(
                "Prioritize processing of pending redemptions"
            )
            if redemption.pending_ratio > Decimal("0.15"):
                recommendations.append(
                    "Consider proactive communication with large redemption requestors"
                )

        if not recommendations:
            recommendations.append("Risk levels are within acceptable ranges")

        return recommendations

    def get_alert(self, alert_id: str) -> RiskAlert | None:
        """Get alert by ID.

        Args:
            alert_id: Alert ID

        Returns:
            Alert or None
        """
        return self._alerts.get(alert_id)

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert.

        Args:
            alert_id: Alert ID

        Returns:
            True if acknowledged
        """
        alert = self._alerts.get(alert_id)
        if not alert:
            return False

        alert.acknowledged_at = datetime.now(timezone.utc)
        return True

    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert.

        Args:
            alert_id: Alert ID

        Returns:
            True if resolved
        """
        alert = self._alerts.get(alert_id)
        if not alert:
            return False

        alert.resolved_at = datetime.now(timezone.utc)
        return True

    def get_active_alerts(
        self,
        risk_type: RiskType | None = None,
        level: RiskLevel | None = None,
    ) -> list[RiskAlert]:
        """Get active (unresolved) alerts.

        Args:
            risk_type: Filter by risk type
            level: Filter by level

        Returns:
            List of active alerts
        """
        alerts = [a for a in self._alerts.values() if a.resolved_at is None]

        if risk_type:
            alerts = [a for a in alerts if a.risk_type == risk_type]

        if level:
            alerts = [a for a in alerts if a.level == level]

        return sorted(alerts, key=lambda a: a.created_at, reverse=True)

    def get_recent_assessments(self, limit: int = 10) -> list[RiskAssessment]:
        """Get recent assessments.

        Args:
            limit: Max assessments to return

        Returns:
            List of recent assessments
        """
        return self._assessments[-limit:][::-1]

    def update_config(self, config: RiskConfig) -> None:
        """Update risk configuration.

        Args:
            config: New configuration
        """
        self.config = config
        logger.info("Risk configuration updated")


# Singleton instance
_risk_service: RiskMonitorService | None = None


def get_risk_monitor_service() -> RiskMonitorService:
    """Get or create risk monitor service singleton."""
    global _risk_service
    if _risk_service is None:
        _risk_service = RiskMonitorService()
    return _risk_service
