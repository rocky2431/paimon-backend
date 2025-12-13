"""API v1 module."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    approvals,
    audit,
    auth,
    fund,
    health,
    metrics,
    rebalancing,
    redemptions,
    reports,
    risk,
    security,
    websocket,
)

api_router = APIRouter()

# Include routers
api_router.include_router(auth.router)
api_router.include_router(redemptions.router)
api_router.include_router(approvals.router)
api_router.include_router(rebalancing.router)
api_router.include_router(risk.router)
api_router.include_router(fund.router)
api_router.include_router(reports.router)
api_router.include_router(websocket.router)
api_router.include_router(audit.router)
api_router.include_router(health.router)
api_router.include_router(metrics.router)
api_router.include_router(security.router)
