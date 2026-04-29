# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

import time
import json
import ipaddress
from typing import Callable
import brotli
import gzip as gzip_lib
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import structlog

from app.core.config import settings
from app.exceptions import DevFlowFixException

logger = structlog.get_logger()


def _extract_first_forwarded_ip(value: str | None) -> str | None:
    if not value:
        return None

    first = value.split(",", 1)[0].strip()
    if not first:
        return None

    try:
        ipaddress.ip_address(first)
    except ValueError:
        return None

    return first


def _is_private_or_loopback_ip(value: str | None) -> bool:
    if not value:
        return False

    try:
        ip_obj = ipaddress.ip_address(value)
    except ValueError:
        return False

    return ip_obj.is_private or ip_obj.is_loopback


def resolve_client_ip(request: Request) -> str:
    """
    Resolve the most useful client IP for proxy deployments.

    When the immediate peer is a local/private proxy (for example nginx behind
    SafeLine), prefer trusted forwarding headers from that proxy. Otherwise use
    the direct peer address.
    """
    direct_ip = request.client.host if request.client else "unknown"

    if not _is_private_or_loopback_ip(direct_ip):
        return direct_ip

    for header_name in ("cf-connecting-ip", "x-real-ip"):
        candidate = request.headers.get(header_name)
        if _extract_first_forwarded_ip(candidate):
            return _extract_first_forwarded_ip(candidate)  # type: ignore[return-value]

    forwarded_for = _extract_first_forwarded_ip(request.headers.get("x-forwarded-for"))
    if forwarded_for:
        return forwarded_for

    return direct_ip

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
            "client_ip": resolve_client_ip(request),
            "direct_client_ip": request.client.host if request.client else None,
            "cf_connecting_ip": request.headers.get("CF-Connecting-IP"),
            "x_forwarded_for": request.headers.get("X-Forwarded-For"),
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

            # Never expose internal error details to external users
            # Error details are logged above for debugging purposes
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "internal_error",
                    "message": "An internal server error occurred. Please contact support with the request ID.",
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
        return resolve_client_ip(request)
    
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
        
        # NOTE: JWT verification is handled by endpoint dependencies (get_current_user),
        # not by this middleware. This is the recommended FastAPI approach.
        # This middleware currently just passes through all requests.
        # If you want global auth middleware, uncomment and implement below:

        # auth_header = request.headers.get("Authorization")
        # if auth_header and auth_header.startswith("Bearer "):
        #     token = auth_header.split(" ")[1]
        #     user = verify_jwt_token(token)  # Implement this
        #     request.state.user = user

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


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware for adding security headers to all responses.

    Implements defense-in-depth security headers including:
    - X-Content-Type-Options: Prevent MIME sniffing
    - X-Frame-Options: Prevent clickjacking
    - Strict-Transport-Security: Force HTTPS
    - Referrer-Policy: Control referrer information
    - Permissions-Policy: Restrict browser features
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and add security headers.

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response with security headers
        """
        response = await call_next(request)

        # Security headers for defense in depth
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # Cache control for API responses (prevent caching of dynamic content)
        if request.url.path not in ["/health", "/ready"]:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        return response


class BrotliOrGzipMiddleware(BaseHTTPMiddleware):
    """
    Smart compression middleware with Brotli (preferred) and Gzip fallback.

    Brotli provides 15-25% better compression than gzip with similar speed.
    Automatically falls back to gzip for older clients that don't support Brotli.

    Performance characteristics:
    - Brotli quality 4: Balanced speed/compression (recommended)
    - Gzip level 6: Balanced speed/compression (fallback)
    - Minimum size: 500 bytes (skip compression for tiny responses)

    Browser support:
    - Brotli: Chrome 50+, Firefox 44+, Safari 11+, Edge 15+ (97%+ coverage)
    - Gzip: All browsers (100% coverage)
    """

    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = 500,
        quality: int = 4,
    ):
        """
        Initialize compression middleware.

        Args:
            app: ASGI application
            minimum_size: Minimum response size to compress (bytes)
            quality: Brotli compression quality 0-11 (4=balanced, 11=max)
        """
        super().__init__(app)
        self.minimum_size = minimum_size
        self.brotli_quality = quality  # 0-11, 4 is balanced (11=max compression)
        self.gzip_level = 6  # 1-9, 6 is balanced

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and compress response if appropriate.

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response (compressed or uncompressed)
        """
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
