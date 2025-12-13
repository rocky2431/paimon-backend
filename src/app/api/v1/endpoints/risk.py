"""Risk monitoring API endpoints."""

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.risk import (
    AlertRouter,
    RiskAlert,
    RiskAssessment,
    RiskConfig,
    RiskLevel,
    RiskMonitorService,
    RiskType,
    get_alert_router,
    get_risk_monitor_service,
)
from app.services.forecasting import (
    ForecastConfig,
    ForecastHorizon,
    ForecastResult,
    LiquidityForecaster,
    get_liquidity_forecaster,
)

router = APIRouter(prefix="/risk", tags=["Risk Monitoring"])


# Request/Response models
class RiskAssessmentRequest(BaseModel):
    """Request for risk assessment."""

    l1_value: Decimal = Field(..., description="L1 tier value")
    total_value: Decimal = Field(..., description="Total portfolio value")
    pending_redemptions: Decimal = Field(
        default=Decimal(0), description="Pending redemption value"
    )
    current_nav: Decimal = Field(..., description="Current NAV")
    nav_24h_change: Decimal = Field(..., description="24h NAV change %")
    nav_7d_volatility: Decimal = Field(
        default=Decimal(0), description="7d volatility"
    )
    asset_allocations: dict[str, Decimal] = Field(
        ..., description="Asset allocations"
    )
    pending_count: int = Field(default=0, description="Pending redemption count")


class RiskDashboard(BaseModel):
    """Risk dashboard overview."""

    overall_level: RiskLevel = Field(..., description="Overall risk level")
    overall_score: int = Field(..., description="Overall risk score")
    liquidity_score: int = Field(..., description="Liquidity risk score")
    price_score: int = Field(..., description="Price risk score")
    concentration_score: int = Field(..., description="Concentration score")
    redemption_score: int = Field(..., description="Redemption score")
    active_alerts_count: int = Field(..., description="Active alerts count")
    last_assessment_id: str | None = Field(None, description="Last assessment ID")


class AlertAcknowledgeRequest(BaseModel):
    """Request to acknowledge an alert."""

    alert_id: str = Field(..., description="Alert ID to acknowledge")


class ForecastRequest(BaseModel):
    """Request for liquidity forecast."""

    horizon: ForecastHorizon = Field(
        default=ForecastHorizon.WEEKLY, description="Forecast horizon"
    )
    current_l1_value: Decimal = Field(..., description="Current L1 value")
    start_date: date | None = Field(None, description="Start date (default: today)")


class HistoricalDataPoint(BaseModel):
    """Historical data point for forecasting."""

    data_date: date = Field(..., description="Date")
    redemption_count: int = Field(..., description="Redemption count")
    redemption_value: Decimal = Field(..., description="Redemption value")


class RiskConfigUpdate(BaseModel):
    """Update for risk configuration."""

    l1_ratio_low: Decimal | None = Field(None, description="L1 low threshold")
    l1_ratio_critical: Decimal | None = Field(None, description="L1 critical threshold")
    nav_vol_high: Decimal | None = Field(None, description="NAV volatility high")
    single_asset_critical: Decimal | None = Field(
        None, description="Single asset critical"
    )
    redemption_critical: Decimal | None = Field(
        None, description="Redemption critical"
    )


# Endpoints
@router.get("/dashboard", response_model=RiskDashboard)
async def get_risk_dashboard() -> RiskDashboard:
    """Get risk dashboard overview.

    Returns current risk levels, scores, and alert counts.
    """
    service = get_risk_monitor_service()
    router_service = get_alert_router()

    # Get recent assessment
    assessments = service.get_recent_assessments(limit=1)

    if assessments:
        latest = assessments[0]
        return RiskDashboard(
            overall_level=latest.overall.overall_level,
            overall_score=latest.overall.overall_score,
            liquidity_score=latest.overall.liquidity_score,
            price_score=latest.overall.price_score,
            concentration_score=latest.overall.concentration_score,
            redemption_score=latest.overall.redemption_score,
            active_alerts_count=len(service.get_active_alerts()),
            last_assessment_id=latest.assessment_id,
        )

    # Return defaults if no assessment
    return RiskDashboard(
        overall_level=RiskLevel.LOW,
        overall_score=20,
        liquidity_score=20,
        price_score=20,
        concentration_score=20,
        redemption_score=20,
        active_alerts_count=0,
        last_assessment_id=None,
    )


@router.post("/assess", response_model=RiskAssessment)
async def perform_risk_assessment(
    request: RiskAssessmentRequest,
) -> RiskAssessment:
    """Perform comprehensive risk assessment.

    Analyzes liquidity, price, concentration, and redemption risks.
    Generates alerts for high/critical risks.
    """
    service = get_risk_monitor_service()

    assessment = service.perform_assessment(
        l1_value=request.l1_value,
        total_value=request.total_value,
        pending_redemptions=request.pending_redemptions,
        current_nav=request.current_nav,
        nav_24h_change=request.nav_24h_change,
        nav_7d_volatility=request.nav_7d_volatility,
        asset_allocations=request.asset_allocations,
        pending_count=request.pending_count,
    )

    # Route alerts through alert router
    alert_router = get_alert_router()
    for alert in assessment.alerts:
        await alert_router.route_alert(alert)

    return assessment


@router.get("/assessment/{assessment_id}")
async def get_assessment(assessment_id: str) -> dict[str, Any]:
    """Get a specific assessment by ID.

    Args:
        assessment_id: Assessment ID
    """
    service = get_risk_monitor_service()
    assessments = service.get_recent_assessments(limit=100)

    for a in assessments:
        if a.assessment_id == assessment_id:
            return a.model_dump()

    raise HTTPException(status_code=404, detail="Assessment not found")


@router.get("/assessments")
async def get_recent_assessments(
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Get recent risk assessments.

    Args:
        limit: Maximum number of assessments
    """
    service = get_risk_monitor_service()
    assessments = service.get_recent_assessments(limit=limit)
    return [a.model_dump() for a in assessments]


# Alert endpoints
@router.get("/alerts", response_model=list[RiskAlert])
async def get_active_alerts(
    risk_type: RiskType | None = None,
    level: RiskLevel | None = None,
) -> list[RiskAlert]:
    """Get active (unresolved) alerts.

    Args:
        risk_type: Filter by risk type
        level: Filter by level
    """
    service = get_risk_monitor_service()
    return service.get_active_alerts(risk_type=risk_type, level=level)


@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: str) -> RiskAlert:
    """Get a specific alert.

    Args:
        alert_id: Alert ID
    """
    service = get_risk_monitor_service()
    alert = service.get_alert(alert_id)

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return alert


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str) -> dict[str, Any]:
    """Acknowledge an alert.

    Args:
        alert_id: Alert ID
    """
    service = get_risk_monitor_service()

    if not service.acknowledge_alert(alert_id):
        raise HTTPException(status_code=404, detail="Alert not found")

    return {"status": "acknowledged", "alert_id": alert_id}


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str) -> dict[str, Any]:
    """Resolve an alert.

    Args:
        alert_id: Alert ID
    """
    service = get_risk_monitor_service()

    if not service.resolve_alert(alert_id):
        raise HTTPException(status_code=404, detail="Alert not found")

    return {"status": "resolved", "alert_id": alert_id}


@router.get("/alerts/history")
async def get_alert_history(
    limit: int = 100,
    risk_type: RiskType | None = None,
) -> list[dict[str, Any]]:
    """Get alert routing history.

    Args:
        limit: Maximum entries
        risk_type: Filter by type
    """
    router_service = get_alert_router()
    return router_service.get_alert_history(limit=limit, risk_type=risk_type)


# Emergency endpoints
@router.get("/emergencies")
async def get_active_emergencies() -> list[dict[str, Any]]:
    """Get active emergency triggers."""
    router_service = get_alert_router()
    emergencies = router_service.get_active_emergencies()
    return [e.model_dump() for e in emergencies]


@router.post("/emergencies/{trigger_id}/execute")
async def execute_emergency(trigger_id: str) -> dict[str, Any]:
    """Execute emergency protocol.

    Args:
        trigger_id: Emergency trigger ID
    """
    router_service = get_alert_router()

    if not router_service.execute_emergency_protocol(trigger_id):
        raise HTTPException(status_code=404, detail="Emergency trigger not found")

    return {"status": "executed", "trigger_id": trigger_id}


@router.post("/emergencies/{trigger_id}/resolve")
async def resolve_emergency(trigger_id: str) -> dict[str, Any]:
    """Resolve emergency.

    Args:
        trigger_id: Emergency trigger ID
    """
    router_service = get_alert_router()

    if not router_service.resolve_emergency(trigger_id):
        raise HTTPException(status_code=404, detail="Emergency trigger not found")

    return {"status": "resolved", "trigger_id": trigger_id}


# Forecasting endpoints
@router.post("/forecast", response_model=ForecastResult)
async def generate_forecast(request: ForecastRequest) -> ForecastResult:
    """Generate liquidity forecast.

    Predicts redemption patterns and liquidity needs.
    """
    forecaster = get_liquidity_forecaster()

    return forecaster.perform_forecast(
        horizon=request.horizon,
        current_l1_value=request.current_l1_value,
        start_date=request.start_date,
    )


@router.get("/forecasts")
async def get_recent_forecasts(
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Get recent forecasts.

    Args:
        limit: Maximum forecasts
    """
    forecaster = get_liquidity_forecaster()
    forecasts = forecaster.get_recent_forecasts(limit=limit)
    return [f.model_dump() for f in forecasts]


@router.post("/forecast/data")
async def add_historical_data(data: list[HistoricalDataPoint]) -> dict[str, Any]:
    """Add historical redemption data for forecasting.

    Args:
        data: List of historical data points
    """
    forecaster = get_liquidity_forecaster()

    for point in data:
        forecaster.add_historical_data(
            date=point.data_date,
            redemption_count=point.redemption_count,
            redemption_value=point.redemption_value,
        )

    return {"status": "added", "count": len(data)}


@router.get("/forecast/patterns")
async def get_detected_patterns() -> dict[str, Any]:
    """Get detected seasonality patterns."""
    forecaster = get_liquidity_forecaster()
    patterns = forecaster.analyze_patterns()

    return {
        pattern_type.value: [p.model_dump() for p in pattern_list]
        for pattern_type, pattern_list in patterns.items()
    }


# Configuration endpoints
@router.get("/config")
async def get_risk_config() -> RiskConfig:
    """Get current risk configuration."""
    service = get_risk_monitor_service()
    return service.config


@router.put("/config")
async def update_risk_config(update: RiskConfigUpdate) -> RiskConfig:
    """Update risk configuration.

    Args:
        update: Config updates
    """
    service = get_risk_monitor_service()
    current = service.config

    # Apply updates
    update_dict = update.model_dump(exclude_none=True)
    new_config = current.model_copy(update=update_dict)

    service.update_config(new_config)
    return new_config


@router.get("/config/forecast")
async def get_forecast_config() -> ForecastConfig:
    """Get forecast configuration."""
    forecaster = get_liquidity_forecaster()
    return forecaster.config


@router.put("/config/forecast")
async def update_forecast_config(config: ForecastConfig) -> ForecastConfig:
    """Update forecast configuration.

    Args:
        config: New config
    """
    forecaster = get_liquidity_forecaster()
    forecaster.update_config(config)
    return config


# Indicator details endpoints
@router.get("/indicators/liquidity")
async def get_liquidity_details(
    l1_value: Decimal,
    total_value: Decimal,
    pending_redemptions: Decimal = Decimal(0),
) -> dict[str, Any]:
    """Get detailed liquidity risk analysis.

    Args:
        l1_value: L1 tier value
        total_value: Total portfolio value
        pending_redemptions: Pending redemptions
    """
    service = get_risk_monitor_service()
    result = service.assess_liquidity_risk(
        l1_value=l1_value,
        total_value=total_value,
        pending_redemptions=pending_redemptions,
    )
    return result.model_dump()


@router.get("/indicators/price")
async def get_price_details(
    current_nav: Decimal,
    nav_24h_change: Decimal,
    nav_7d_volatility: Decimal = Decimal(0),
    nav_30d_volatility: Decimal = Decimal(0),
    max_drawdown: Decimal = Decimal(0),
) -> dict[str, Any]:
    """Get detailed price risk analysis.

    Args:
        current_nav: Current NAV
        nav_24h_change: 24h change
        nav_7d_volatility: 7d volatility
        nav_30d_volatility: 30d volatility
        max_drawdown: Max drawdown
    """
    service = get_risk_monitor_service()
    result = service.assess_price_risk(
        current_nav=current_nav,
        nav_24h_change=nav_24h_change,
        nav_7d_volatility=nav_7d_volatility,
        nav_30d_volatility=nav_30d_volatility,
        max_drawdown=max_drawdown,
    )
    return result.model_dump()


@router.post("/indicators/concentration")
async def get_concentration_details(
    allocations: dict[str, Decimal],
) -> dict[str, Any]:
    """Get detailed concentration risk analysis.

    Args:
        allocations: Asset allocations
    """
    service = get_risk_monitor_service()
    result = service.assess_concentration_risk(allocations)
    return result.model_dump()


@router.get("/indicators/redemption")
async def get_redemption_details(
    pending_count: int,
    pending_value: Decimal,
    total_aum: Decimal,
) -> dict[str, Any]:
    """Get detailed redemption pressure analysis.

    Args:
        pending_count: Pending count
        pending_value: Pending value
        total_aum: Total AUM
    """
    service = get_risk_monitor_service()
    result = service.assess_redemption_pressure(
        pending_count=pending_count,
        pending_value=pending_value,
        total_aum=total_aum,
    )
    return result.model_dump()
