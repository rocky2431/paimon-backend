"""FastAPI application factory and main entry point."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import api_router
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup/shutdown events."""
    # Startup
    settings = get_settings()
    app.state.settings = settings

    yield

    # Shutdown
    pass


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Paimon Prime Fund Backend API",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    register_routes(app)

    return app


def register_routes(app: FastAPI) -> None:
    """Register all application routes."""
    settings = get_settings()

    # Include API router
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health", tags=["System"])
    async def health_check():
        """Health check endpoint for load balancers and monitoring."""
        return {
            "status": "healthy",
            "version": __version__,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get(f"{get_settings().api_v1_prefix}/", tags=["API"])
    async def api_root():
        """API root endpoint with application info."""
        settings = get_settings()
        return {
            "name": settings.app_name,
            "version": __version__,
            "environment": settings.environment,
            "docs_url": "/docs" if settings.debug else "Disabled in production",
        }


# Create application instance
app = create_app()
