# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

import time
import json
from typing import Callable
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import structlog

from app.core.config import settings
from app.exceptions import DevFlowFixException

logger = structlog.get_logger()

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for logging HTTP requests and responses.
    
    Logs:
    - Request method, path, query params, headers
    - Response status code, duration
    - Request/response body (if configured)
    """
    def __init__(
        self,
        app: ASGIApp,
        log_request_body: bool = False,
        log_response_body: bool = False,
        exclude_paths: list[str] = None,
    ):
        """
        Initialize middleware.
        
        Args:
            app: ASGI application
            log_request_body: Whether to log request body
            log_response_body: Whether to log response body
            exclude_paths: Paths to exclude from logging
        """
        super().__init__(app)
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body
        self.exclude_paths = exclude_paths or ["/health", "/ready"]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and log details.
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response
        """
        # Skip logging for excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)
        
        # Generate request ID if not present
        request_id = request.headers.get("X-Request-ID", f"req_{int(time.time() * 1000)}")
        
        # Start timer
        start_time = time.time()
        
        # Log request
        log_data = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("User-Agent"),
        }
        
        # Optionally log request body
        if self.log_request_body and request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if body:
                    log_data["request_body"] = body.decode("utf-8")[:1000]  # Limit size
            except Exception:
                pass  # Ignore body logging errors
        
        logger.info("request_started", **log_data)
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Log response
            logger.info(
                "request_completed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as exc:
            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Log error
            logger.error(
                "request_failed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                error=str(exc),
                exc_info=True,
            )
            
            # Re-raise to let error handler deal with it
            raise

class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for handling exceptions and converting them to JSON responses.
    
    Catches all exceptions and returns consistent error responses.
    """
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and handle errors.
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response
        """
        try:
            return await call_next(request)
            
        except DevFlowFixException as exc:
            # Handle custom exceptions
            logger.warning(
                "application_error",
                request_id=getattr(request.state, "request_id", None),
                error_code=exc.error_code,
                error=str(exc),
                details=exc.details,
            )
            
            # Determine status code based on error type
            status_code = self._get_status_code_for_exception(exc)
            
            return JSONResponse(
                status_code=status_code,
                content=exc.to_dict(),
            )
            
        except Exception as exc:
            # Handle unexpected exceptions
            request_id = getattr(request.state, "request_id", "unknown")
            
            logger.error(
                "unhandled_exception",
                request_id=request_id,
                path=request.url.path,
                error=str(exc),
                exc_info=True,
            )
            
            # Don't expose internal errors in production
            detail = str(exc) if settings.environment != "prod" else "Internal server error"
            
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "internal_error",
                    "message": detail,
                    "request_id": request_id,
                },
            )
    
    def _get_status_code_for_exception(self, exc: DevFlowFixException) -> int:
        """
        Map exception type to HTTP status code.
        
        Args:
            exc: Exception instance
            
        Returns:
            HTTP status code
        """
        from app.exceptions import (
            IncidentNotFoundError,
            RateLimitExceededError,
            ApprovalRequiredError,
            ValidationFailedError,
            ConfigurationError,
            WebhookValidationError,
        )
        
        # Map exception types to status codes
        if isinstance(exc, IncidentNotFoundError):
            return status.HTTP_404_NOT_FOUND
        elif isinstance(exc, RateLimitExceededError):
            return status.HTTP_429_TOO_MANY_REQUESTS
        elif isinstance(exc, (ApprovalRequiredError, ValidationFailedError)):
            return status.HTTP_400_BAD_REQUEST
        elif isinstance(exc, (ConfigurationError, WebhookValidationError)):
            return status.HTTP_400_BAD_REQUEST
        else:
            return status.HTTP_500_INTERNAL_SERVER_ERROR

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Basic rate limiting middleware.
    
    Note: For production, use Redis-based rate limiting.
    This is a simple in-memory implementation for development.
    """
    def __init__(
        self,
        app: ASGIApp,
        requests_per_minute: int = 60,
        exclude_paths: list[str] = None,
    ):
        """
        Initialize middleware.
        
        Args:
            app: ASGI application
            requests_per_minute: Rate limit per client
            exclude_paths: Paths to exclude from rate limiting
        """
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.exclude_paths = exclude_paths or ["/health", "/ready"]
        
        # In-memory storage (use Redis in production)
        self.request_counts = {}
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and enforce rate limit.
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response
        """
        # Skip rate limiting for excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)
        
        # Get client identifier (IP or user ID)
        client_id = self._get_client_id(request)
        
        # Check rate limit
        if self._is_rate_limited(client_id):
            logger.warning(
                "rate_limit_exceeded",
                client_id=client_id,
                path=request.url.path,
            )
            
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded: {self.requests_per_minute} requests per minute",
                    "retry_after": 60,
                },
                headers={"Retry-After": "60"},
            )
        
        # Record request
        self._record_request(client_id)
        
        # Process request
        return await call_next(request)
    
    def _get_client_id(self, request: Request) -> str:
        """Get client identifier from request."""
        # In production, use authenticated user ID
        # For now, use IP address
        return request.client.host if request.client else "unknown"
    
    def _is_rate_limited(self, client_id: str) -> bool:
        """Check if client has exceeded rate limit."""
        # This is a simplified implementation
        # In production, use a proper rate limiting algorithm with Redis
        current_time = int(time.time())
        minute_bucket = current_time // 60
        
        key = f"{client_id}:{minute_bucket}"
        count = self.request_counts.get(key, 0)
        
        return count >= self.requests_per_minute
    
    def _record_request(self, client_id: str):
        """Record a request for rate limiting."""
        current_time = int(time.time())
        minute_bucket = current_time // 60
        
        key = f"{client_id}:{minute_bucket}"
        self.request_counts[key] = self.request_counts.get(key, 0) + 1
        
        # Clean up old buckets (keep last 2 minutes)
        old_buckets = [
            k for k in self.request_counts.keys()
            if int(k.split(":")[1]) < minute_bucket - 1
        ]
        for k in old_buckets:
            del self.request_counts[k]

class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Middleware for authenticating requests.
    
    Note: This is a placeholder. Implement proper JWT/OAuth authentication.
    """
    def __init__(
        self,
        app: ASGIApp,
        exclude_paths: list[str] = None,
    ):
        """
        Initialize middleware.
        
        Args:
            app: ASGI application
            exclude_paths: Paths to exclude from authentication
        """
        super().__init__(app)
        self.exclude_paths = exclude_paths or [
            "/health",
            "/ready",
            "/",
            "/docs",
            "/openapi.json",
            "/webhook",  # Webhooks use signature verification
        ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and verify authentication.
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response
        """
        # Skip authentication for excluded paths
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)
        
        # Get authorization header
        auth_header = request.headers.get("Authorization")
        
        # For now, just pass through
        # TODO: Implement proper JWT verification
        if auth_header and auth_header.startswith("Bearer "):
            # Extract and verify token
            # token = auth_header.split(" ")[1]
            # user = verify_jwt_token(token)
            # request.state.user = user
            pass
        
        # Process request
        return await call_next(request)

class PerformanceMonitoringMiddleware(BaseHTTPMiddleware):
    """
    Middleware for monitoring request performance.
    
    Tracks slow requests and collects metrics.
    """
    def __init__(
        self,
        app: ASGIApp,
        slow_request_threshold_ms: int = 1000,
    ):
        """
        Initialize middleware.
        
        Args:
            app: ASGI application
            slow_request_threshold_ms: Threshold for slow request warning
        """
        super().__init__(app)
        self.slow_request_threshold_ms = slow_request_threshold_ms
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and monitor performance.
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response
        """
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Log slow requests
        if duration_ms > self.slow_request_threshold_ms:
            logger.warning(
                "slow_request",
                request_id=getattr(request.state, "request_id", None),
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                threshold_ms=self.slow_request_threshold_ms,
            )
        
        # Add performance headers
        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        
        return response

class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware for adding request IDs to all requests.
    
    Generates or extracts request ID from header.
    """
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and add request ID.
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response
        """
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = f"req_{int(time.time() * 1000000)}"
        
        # Store in request state
        request.state.request_id = request_id
        
        # Process request
        response = await call_next(request)
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response