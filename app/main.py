# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Request, status, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from sqlalchemy import text
from sqlalchemy.orm import Session
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

app.add_middleware(RequestIDMiddleware)

app.add_middleware(
    PerformanceMonitoringMiddleware,
    slow_request_threshold_ms=1000,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time"],
)

app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,
)

app.add_middleware(
    RequestLoggingMiddleware,
    log_request_body=settings.log_level == "DEBUG",
    log_response_body=False,
    exclude_paths=["/health", "/ready"],
)

if settings.is_production:
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        exclude_paths=["/health", "/ready"],
    )

app.add_middleware(ErrorHandlingMiddleware)


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
            "timestamp": datetime.utcnow().isoformat(),
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
            "timestamp": datetime.utcnow().isoformat(),
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
)
async def health_check():
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
            "timestamp": datetime.utcnow().isoformat(),
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
        },
    }


from app.api.v1.webhook import router as webhook_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.auth import router as auth_router
from app.api.v1.incidents import router as incidents_router

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

@app.post("/webhooks/github", tags=["Webhooks"])
async def github_webhook_root(
    request: Request,
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event"),
    x_github_delivery: Optional[str] = Header(None, alias="X-GitHub-Delivery"),
):
    """
    Root GitHub webhook endpoint.
    """
    from app.api.v1.webhook import receive_github_webhook, verify_github_webhook_signature
    from app.dependencies import get_db, get_event_processor
    from fastapi import BackgroundTasks
    
    event_type = str(x_github_event) if x_github_event else "unknown"
    delivery_id = str(x_github_delivery) if x_github_delivery else None
    
    body = await verify_github_webhook_signature(request)
    
    db = next(get_db())
    try:
        event_processor = get_event_processor(db)
        background_tasks = BackgroundTasks()
        
        return await receive_github_webhook(
            request=request,
            background_tasks=background_tasks,
            x_github_event=event_type,
            x_github_delivery=delivery_id,
            body=body,
            db=db,
            event_processor=event_processor,
        )
    finally:
        db.close()


@app.post("/webhooks/argocd", tags=["Webhooks"])
async def argocd_webhook_root(
    request: Request,
    db: Session = Depends(get_db),
):
    from app.api.v1.webhook import receive_argocd_webhook
    
    payload = await request.json()
    event_processor = get_event_processor(db)
    
    from fastapi import BackgroundTasks
    background_tasks = BackgroundTasks()
    
    return await receive_argocd_webhook(
        request=request,
        background_tasks=background_tasks,
        payload=payload,
        db=db,
        event_processor=event_processor,
    )


@app.post("/webhooks/kubernetes", tags=["Webhooks"])
async def kubernetes_webhook_root(
    request: Request,
    db: Session = Depends(get_db),
):
    from app.api.v1.webhook import receive_kubernetes_webhook
    
    payload = await request.json()
    event_processor = get_event_processor(db)
    
    from fastapi import BackgroundTasks
    background_tasks = BackgroundTasks()
    
    return await receive_kubernetes_webhook(
        request=request,
        background_tasks=background_tasks,
        payload=payload,
        db=db,
        event_processor=event_processor,
    )


logger.info(
    "routers_registered",
    routers=[
        "/api/v1/auth",
        "/api/v1/incidents"
        "/api/v1/webhook",
        "/api/v1/analytics",
        "/webhooks/github",
        "/webhooks/argocd",
        "/webhooks/kubernetes",
    ],
)
