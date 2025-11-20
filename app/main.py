# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request, status, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
import structlog

from app.core.config import settings
from app.core.schemas.common import HealthResponse
from app.exceptions import DevFlowFixException
from app.middleware import (
    RequestIDMiddleware,
    RequestLoggingMiddleware,
    ErrorHandlingMiddleware,
    RateLimitMiddleware,
    PerformanceMonitoringMiddleware,
)
from app.dependencies import get_engine

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer() if settings.is_production 
        else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    
    Handles startup and shutdown events.
    """
    # Startup
    logger.info(
        "application_startup",
        environment=settings.environment.value,
        version=settings.version,
        database_url=settings.database_url.split("@")[-1],  # Hide credentials
    )
    
    # Initialize database connection
    try:
        engine = get_engine()
        with engine.connect() as conn:
            logger.info("database_connection_verified")
    except Exception as e:
        logger.error("database_connection_failed", error=str(e))
        # Continue anyway - app can still serve health checks
    
    # TODO: Initialize cache connections (Redis)
    # TODO: Pre-warm any connections
    # TODO: Load initial configuration
    
    yield
    
    # Shutdown
    logger.info("application_shutdown")
    
    # TODO: Close database connections
    # TODO: Close cache connections
    # TODO: Cleanup resources

app = FastAPI(
    title="DevFlowFix",
    description="Autonomous AI agent for CI/CD failure detection, analysis, and remediation",
    version=settings.version,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

""" Middleware (!Order matters) """
# 1. Request ID (should be first to ensure all logs have request ID)
app.add_middleware(RequestIDMiddleware)

# 2. Performance Monitoring
app.add_middleware(
    PerformanceMonitoringMiddleware,
    slow_request_threshold_ms=1000,
)

# 3. CORS (before any request processing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time"],
)

# 4. GZip Compression (compress responses > 1KB)
app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,
)

# 5. Request Logging
app.add_middleware(
    RequestLoggingMiddleware,
    log_request_body=settings.log_level == "DEBUG",
    log_response_body=False,
    exclude_paths=["/health", "/ready"],
)

# 6. Rate Limiting (before error handling)
if settings.is_production:
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        exclude_paths=["/health", "/ready"],
    )

# 7. Error Handling (should be last to catch all errors)
app.add_middleware(ErrorHandlingMiddleware)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle Pydantic validation errors.
    
    Returns user-friendly validation error messages.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.warning(
        "validation_error",
        request_id=request_id,
        path=request.url.path,
        errors=exc.errors(),
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "message": "Request validation failed",
            "errors": exc.errors(),
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

@app.exception_handler(DevFlowFixException)
async def devflowfix_exception_handler(request: Request, exc: DevFlowFixException):
    """
    Handle custom DevFlowFix exceptions.
    
    Already handled by ErrorHandlingMiddleware, but keeping for explicit handling.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.warning(
        "application_error",
        request_id=request_id,
        error_code=exc.error_code,
        error=str(exc),
        details=exc.details,
    )
    
    # Determine status code
    from app.exceptions import (
        IncidentNotFoundError,
        RateLimitExceededError,
        ApprovalRequiredError,
    )
    
    if isinstance(exc, IncidentNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, RateLimitExceededError):
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
    elif isinstance(exc, ApprovalRequiredError):
        status_code = status.HTTP_400_BAD_REQUEST
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    
    return JSONResponse(
        status_code=status_code,
        content={
            **exc.to_dict(),
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """
    Handle all other unhandled exceptions.
    
    Catches any exceptions not handled by specific handlers.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.error(
        "unhandled_exception",
        request_id=request_id,
        path=request.url.path,
        error=str(exc),
        exc_info=True,
    )
    
    # Don't expose internal errors in production
    detail = str(exc) if not settings.is_production else "Internal server error"
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_error",
            "message": detail,
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Health check",
    description="Basic health check endpoint to verify service is running",
)
async def health_check():
    """
    Health check endpoint.
    
    Returns basic health status of the service.
    Always returns 200 OK if the service is running.
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        version=settings.version,
    )


@app.get(
    "/ready",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Readiness check",
    description="Readiness check with external dependency verification",
)
async def readiness_check():
    """
    Readiness check endpoint.
    
    Checks if service is ready to handle requests by verifying:
    - Database connection
    - External API connectivity (optional)
    - Cache availability (optional)
    
    Returns 200 if healthy, 503 if any critical component is down.
    """
    health_status = "healthy"
    components = {}
    
    # Check database connection
    try:
        from app.dependencies import get_engine
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        components["database"] = "healthy"
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        components["database"] = "unhealthy"
        health_status = "degraded"
    
    # Check NVIDIA API (optional - don't fail if not configured)
    if settings.nvidia_api_key:
        try:
            # TODO: Implement actual NVIDIA API health check
            components["nvidia_api"] = "healthy"
        except Exception as e:
            logger.error("nvidia_api_health_check_failed", error=str(e))
            components["nvidia_api"] = "unhealthy"
            # Don't mark as degraded - this is optional
    
    # Check Redis cache (optional)
    if settings.redis_url:
        try:
            # TODO: Implement Redis health check
            components["cache"] = "healthy"
        except Exception as e:
            logger.error("cache_health_check_failed", error=str(e))
            components["cache"] = "unhealthy"
            # Cache is optional, so don't mark as degraded
    
    # Return appropriate status code
    status_code = (
        status.HTTP_200_OK if health_status == "healthy" 
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    
    return JSONResponse(
        status_code=status_code,
        content={
            "status": health_status,
            "timestamp": datetime.utcnow().isoformat(),
            "version": settings.version,
            **components,
        },
    )


@app.get(
    "/",
    tags=["Root"],
    summary="Root endpoint",
    description="API information and navigation",
)
async def root():
    """
    Root endpoint.
    
    Returns basic API information and navigation links.
    """
    return {
        "name": "DevFlowFix API",
        "version": settings.version,
        "environment": settings.environment.value,
        "description": "Autonomous AI agent for CI/CD failure remediation",
        "links": {
            "docs": "/docs" if not settings.is_production else None,
            "redoc": "/redoc" if not settings.is_production else None,
            "health": "/health",
            "ready": "/ready",
        },
    }

# Import and register routers when ready
# TODO: Implement routers

# from app.api.v1.router import api_router
# app.include_router(api_router, prefix="/api/v1", tags=["v1"])

# Example router registration (uncomment when routers are ready):
# from app.api.v1 import health, incidents, webhook, analytics, approvals
from app.api.v1.webhook import router as webhook_router, receive_github_webhook

# Register webhook router at /api/v1/webhook/*
app.include_router(
    webhook_router,
    prefix="/api/v1",
    tags=["Webhooks"]
)

# Also register GitHub webhook at root /webhooks/github for convenience
# Direct route registration for the commonly expected path
@app.post("/webhooks/github", tags=["Webhooks"])
async def github_webhook_root(request: Request, x_github_event: str | None = Header(None), x_github_delivery: str | None = Header(None), x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256")):
    """GitHub webhook endpoint at root level (redirects to main handler)."""
    return await receive_github_webhook(request, x_github_event, x_github_delivery, x_hub_signature_256)

logger.info("webhook_routers_registered", prefixes=["/api/v1/webhook", "/webhooks/github"])
# 
# app.include_router(
#     health.router,
#     prefix="/api/v1",
#     tags=["Health"]
# )
# 
# app.include_router(
#     incidents.router,
#     prefix="/api/v1",
#     tags=["Incidents"]
# )
# 
# app.include_router(
#     webhook.router,
#     prefix="/api/v1",
#     tags=["Webhooks"]
# )
# 
# app.include_router(
#     analytics.router,
#     prefix="/api/v1",
#     tags=["Analytics"]
# )
# 
# app.include_router(
#     approvals.router,
#     prefix="/api/v1",
#     tags=["Approvals"]
# )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.value.lower(),
        access_log=True,
    )