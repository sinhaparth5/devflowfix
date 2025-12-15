# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
import asyncio
import brotli
import gzip as gzip_lib
from fastapi import FastAPI, Request, status, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import ORJSONResponse, JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
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
from app.dependencies import get_engine, get_db, get_event_processor

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


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Security headers for defense in depth
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # Cache control for API responses
        if request.url.path not in ["/health", "/ready"]:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


class BrotliOrGzipMiddleware(BaseHTTPMiddleware):
    """
    Smart compression middleware with Brotli (preferred) and Gzip fallback.

    Brotli provides 15-25% better compression than gzip with similar speed.
    Falls back to gzip for older clients.
    """

    def __init__(self, app, minimum_size: int = 500, quality: int = 4):
        super().__init__(app)
        self.minimum_size = minimum_size
        self.brotli_quality = quality  # 0-11, 4 is balanced (11=max compression)
        self.gzip_level = 6  # 1-9, 6 is balanced

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Don't compress if already compressed or too small
        if (
            "content-encoding" in response.headers
            or "content-length" not in response.headers
            or int(response.headers.get("content-length", 0)) < self.minimum_size
        ):
            return response

        # Parse Accept-Encoding header
        accept_encoding = request.headers.get("accept-encoding", "").lower()

        # Get response body
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        # Skip if body is too small
        if len(body) < self.minimum_size:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        # Try Brotli first (best compression)
        if "br" in accept_encoding:
            compressed_body = brotli.compress(body, quality=self.brotli_quality)
            encoding = "br"
        # Fallback to gzip
        elif "gzip" in accept_encoding:
            compressed_body = gzip_lib.compress(body, compresslevel=self.gzip_level)
            encoding = "gzip"
        else:
            # No compression supported by client
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        # Build new response with compressed body
        headers = dict(response.headers)
        headers["content-encoding"] = encoding
        headers["content-length"] = str(len(compressed_body))
        headers["vary"] = "Accept-Encoding"

        return Response(
            content=compressed_body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "application_startup",
        environment=settings.environment.value,
        version=settings.version,
        database_url=settings.database_url.split("@")[-1],
    )
    
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            logger.info("database_connection_verified")
    except Exception as e:
        logger.error("database_connection_failed", error=str(e))
    
    yield
    
    logger.info("application_shutdown")


app = FastAPI(
    title="DevFlowFix",
    description="Autonomous AI agent for CI/CD failure detection, analysis, and remediation",
    version=settings.version,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
    default_response_class=ORJSONResponse,  # ORJSON is 2-3x faster than stdlib json
    swagger_ui_parameters={
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
        "tryItOutEnabled": True,
    },
    generate_unique_id_function=lambda route: f"{route.tags[0]}-{route.name}" if route.tags else route.name,
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="DevFlowFix API",
        version=settings.version,
        description="Autonomous AI agent for CI/CD failure detection, analysis, and remediation",
        routes=app.routes,
    )
    
    openapi_schema["components"]["securitySchemes"] = {
        "HTTPBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter your JWT token from /api/v1/auth/login"
        }
    }
    
    openapi_schema["security"] = [{"HTTPBearer": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# Middleware order matters! Applied in reverse order (last added = first executed)
# Order: Error Handling -> Rate Limiting -> Logging -> Compression -> CORS -> Security -> Performance -> Request ID

# 1. Error handling (catch all errors)
app.add_middleware(ErrorHandlingMiddleware)

# 2. Rate limiting (block bad actors early)
if settings.is_production:
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=120,  # Increased for better throughput
        exclude_paths=["/health", "/ready"],
    )

# 3. Request logging (log after rate limiting)
app.add_middleware(
    RequestLoggingMiddleware,
    log_request_body=settings.log_level == "DEBUG",
    log_response_body=False,
    exclude_paths=["/health", "/ready"],
)

# 4. Brotli/Gzip compression (compress responses with best algorithm)
# Brotli is 15-25% better than gzip, falls back to gzip for older clients
app.add_middleware(
    BrotliOrGzipMiddleware,
    minimum_size=500,  # Compress responses > 500 bytes
    quality=4,  # Brotli quality 0-11 (4=balanced, 11=max compression)
)

# 5. CORS (handle cross-origin requests)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time"],
    max_age=3600,  # Cache preflight requests for 1 hour
)

# 6. Trusted host (prevent host header attacks)
if settings.is_production and settings.allowed_hosts:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts.split(",") if isinstance(settings.allowed_hosts, str) else settings.allowed_hosts,
    )

# 7. Security headers (add security headers to responses)
app.add_middleware(SecurityHeadersMiddleware)

# 8. Performance monitoring (track request timing)
app.add_middleware(
    PerformanceMonitoringMiddleware,
    slow_request_threshold_ms=2000,  # Increased threshold for complex operations
)

# 9. Request ID (first middleware, adds ID to all requests)
app.add_middleware(RequestIDMiddleware)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.exception_handler(DevFlowFixException)
async def devflowfix_exception_handler(request: Request, exc: DevFlowFixException):
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.warning(
        "application_error",
        request_id=request_id,
        error_code=exc.error_code,
        error=str(exc),
        details=exc.details,
    )
    
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")

    logger.error(
        "unhandled_exception",
        request_id=request_id,
        path=request.url.path,
        error=str(exc),
        exc_info=True,
    )

    # Never expose internal error details to external users
    # Error details are logged above for debugging purposes
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_error",
            "message": "An internal server error occurred. Please contact support with the request ID.",
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Health check",
)
async def health_check():
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc),
        version=settings.version,
    )


@app.get(
    "/ready",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Readiness check",
)
async def readiness_check():
    health_status = "healthy"
    components = {}
    
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        components["database"] = "healthy"
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        components["database"] = "unhealthy"
        health_status = "degraded"
    
    if settings.nvidia_api_key:
        components["nvidia_api"] = "configured"
    
    if settings.redis_url:
        components["cache"] = "configured"
    
    status_code = (
        status.HTTP_200_OK if health_status == "healthy" 
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    
    return JSONResponse(
        status_code=status_code,
        content={
            "status": health_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": settings.version,
            **components,
        },
    )


@app.get(
    "/",
    tags=["Root"],
    summary="Root endpoint",
)
async def root():
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
            "api": "/api/v1",
        },
        "endpoints": {
            "auth": "/api/v1/auth",
            "webhooks": "/api/v1/webhook",
            "analytics": "/api/v1/analytics",
            "incidents": "/api/v1/incidents",
            "user_details": "/api/v1/user-details",
        },
    }


from app.api.v1.webhook import router as webhook_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.auth import router as auth_router
from app.api.v1.incidents import router as incidents_router
from app.api.v1.user_details import router as user_details_router

app.include_router(
    auth_router,
    prefix="/api/v1",
    tags=["Authentication"],
)

app.include_router(
    incidents_router,
    prefix="/api/v1",
    tags=["Incidents"],
)

app.include_router(
    webhook_router,
    prefix="/api/v1",
    tags=["Webhooks"],
)

app.include_router(
    analytics_router,
    prefix="/api/v1",
    tags=["Analytics"],
)

app.include_router(
    user_details_router,
    prefix="/api/v1",
    tags=["User Details"],
)

logger.info(
    "routers_registered",
    routers=[
        "/api/v1/auth",
        "/api/v1/incidents",
        "/api/v1/webhook",
        "/api/v1/analytics",
        "/api/v1/user-details",
    ],
    webhook_endpoints=[
        "/api/v1/webhook/github/{user_id}",
        "/api/v1/webhook/argocd/{user_id}",
        "/api/v1/webhook/kubernetes/{user_id}",
        "/api/v1/webhook/generic/{user_id}",
    ]
)
