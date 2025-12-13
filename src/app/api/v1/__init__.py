"""API v1 module."""

from fastapi import APIRouter

from app.api.v1.endpoints import approvals, auth, redemptions

api_router = APIRouter(prefix="/v1")

# Include routers
api_router.include_router(auth.router)
api_router.include_router(redemptions.router)
api_router.include_router(approvals.router)
