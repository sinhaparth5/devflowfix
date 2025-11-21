# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Circuit Breaker Pattern Implementation

Prevents cascading failures by stopping requests to failing services.
Opens the circuit after a threshold of failures, allowing time for recovery.
"""

import time
from enum import Enum
from typing import Callable, Any, Optional
from functools import wraps
from dataclasses import dataclass, field

from app.utils.logging import get_logger

logger = get_logger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed" 
    OPEN = "open" 
    HALF_OPEN = "half_open" 


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5 
    success_threshold: int = 2 
    timeout: float = 60.0 
    expected_exception: type = Exception


@dataclass
class CircuitBreakerStats:
    """Circuit breaker statistics."""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_state_change: float = field(default_factory=time.time)
    total_requests: int = 0
    total_failures: int = 0
    total_successes: int = 0


class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures.
    
    States:
    - CLOSED: Normal operation, all requests pass through
    - OPEN: Too many failures, blocking all requests
    - HALF_OPEN: Testing if service recovered, limited requests allowed
    
    Example:
        ```python
        circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            timeout=60.0
        )
        
        @circuit_breaker
        async def call_external_service():
            # Your API call here
            pass
        ```
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 60.0,
        expected_exception: type = Exception,
        name: Optional[str] = None,
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            success_threshold: Number of successes to close from half-open
            timeout: Seconds to wait before trying half-open
            expected_exception: Exception type to catch
            name: Optional name for logging
        """
        self.config = CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout=timeout,
            expected_exception=expected_exception,
        )
        self.stats = CircuitBreakerStats()
        self.name = name or "circuit_breaker"
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator to wrap function with circuit breaker."""
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            return await self._call_async(func, *args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            return self._call_sync(func, *args, **kwargs)
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    async def _call_async(self, func: Callable, *args, **kwargs) -> Any:
        """Execute async function with circuit breaker protection."""
        self.stats.total_requests += 1
        
        if self.stats.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._transition_to_half_open()
            else:
                logger.warning(
                    "circuit_breaker_open",
                    name=self.name,
                    failure_count=self.stats.failure_count,
                )
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is OPEN"
                )
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        
        except self.config.expected_exception as e:
            self._on_failure()
            raise
    
    def _call_sync(self, func: Callable, *args, **kwargs) -> Any:
        """Execute sync function with circuit breaker protection."""
        self.stats.total_requests += 1
        
        if self.stats.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._transition_to_half_open()
            else:
                logger.warning(
                    "circuit_breaker_open",
                    name=self.name,
                    failure_count=self.stats.failure_count,
                )
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is OPEN"
                )
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        
        except self.config.expected_exception as e:
            self._on_failure()
            raise
    
    def _on_success(self) -> None:
        """Handle successful call."""
        self.stats.total_successes += 1
        
        if self.stats.state == CircuitState.HALF_OPEN:
            self.stats.success_count += 1
            
            if self.stats.success_count >= self.config.success_threshold:
                self._transition_to_closed()
    
    def _on_failure(self) -> None:
        """Handle failed call."""
        self.stats.total_failures += 1
        self.stats.failure_count += 1
        self.stats.last_failure_time = time.time()
        
        logger.warning(
            "circuit_breaker_failure",
            name=self.name,
            failure_count=self.stats.failure_count,
            threshold=self.config.failure_threshold,
            state=self.stats.state.value,
        )
        
        if self.stats.state == CircuitState.HALF_OPEN:
            self._transition_to_open()
        
        elif self.stats.failure_count >= self.config.failure_threshold:
            self._transition_to_open()
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to try half-open."""
        if self.stats.last_failure_time is None:
            return False
        
        time_since_failure = time.time() - self.stats.last_failure_time
        return time_since_failure >= self.config.timeout
    
    def _transition_to_open(self) -> None:
        """Transition to OPEN state."""
        self.stats.state = CircuitState.OPEN
        self.stats.last_state_change = time.time()
        
        logger.error(
            "circuit_breaker_opened",
            name=self.name,
            failure_count=self.stats.failure_count,
            threshold=self.config.failure_threshold,
        )
    
    def _transition_to_half_open(self) -> None:
        """Transition to HALF_OPEN state."""
        self.stats.state = CircuitState.HALF_OPEN
        self.stats.success_count = 0
        self.stats.last_state_change = time.time()
        
        logger.info(
            "circuit_breaker_half_open",
            name=self.name,
        )
    
    def _transition_to_closed(self) -> None:
        """Transition to CLOSED state."""
        self.stats.state = CircuitState.CLOSED
        self.stats.failure_count = 0
        self.stats.success_count = 0
        self.stats.last_state_change = time.time()
        
        logger.info(
            "circuit_breaker_closed",
            name=self.name,
            total_successes=self.stats.total_successes,
        )
    
    def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state."""
        self.stats.state = CircuitState.CLOSED
        self.stats.failure_count = 0
        self.stats.success_count = 0
        self.stats.last_failure_time = None
        
        logger.info("circuit_breaker_reset", name=self.name)
    
    def get_state(self) -> CircuitState:
        """Get current circuit state."""
        return self.stats.state
    
    def get_stats(self) -> dict:
        """Get circuit breaker statistics."""
        return {
            "state": self.stats.state.value,
            "failure_count": self.stats.failure_count,
            "success_count": self.stats.success_count,
            "total_requests": self.stats.total_requests,
            "total_failures": self.stats.total_failures,
            "total_successes": self.stats.total_successes,
            "last_failure_time": self.stats.last_failure_time,
            "last_state_change": self.stats.last_state_change,
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass
