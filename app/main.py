from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.api.auth import router as auth_router
from app.api.geofences import router as geofences_router
from app.api.devices import router as devices_router
from app.api.routing import router as routing_router
from app.api.recommendations import router as recommendations_router
from app.api.monitoring import router as monitoring_router
from app.utils.middleware import RateLimitMiddleware, LoggingMiddleware, SecurityHeadersMiddleware

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="A production-ready geospatial analytics API for real-time location intelligence",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trusted host middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "*.localhost"],
)

# Custom middleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RateLimitMiddleware)

# Include routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(geofences_router, prefix="/api/v1")
app.include_router(devices_router, prefix="/api/v1/devices", tags=["devices"])
app.include_router(routing_router, prefix="/api/v1/routes", tags=["routing"])
app.include_router(recommendations_router, prefix="/api/v1/recommendations", tags=["recommendations"])
app.include_router(monitoring_router, prefix="/api/v1/monitoring", tags=["monitoring"])


@app.get("/")
async def root():
    return {
        "message": "Welcome to GeoInsight API",
        "version": settings.app_version,
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.environment,
        "version": settings.app_version
    }