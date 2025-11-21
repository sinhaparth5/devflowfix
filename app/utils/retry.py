# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Retry Utilities with Exponential Backoff

Provides decorators and utilities for retrying failed operations.
"""

import asyncio
import time
from typing import Callable, Any, Optional, Type, Tuple
from functools import wraps

from app.utils.logging import get_logger

logger = get_logger(__name__)


def calculate_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential: bool = True,
    jitter: bool = True,
) -> float:
    """
    Calculate retry delay with exponential backoff and optional jitter.
    
    Args:
        attempt: Current attempt number (0-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        exponential: Use exponential backoff
        jitter: Add random jitter to prevent thundering herd
        
    Returns:
        Delay in seconds
    """
    if exponential:
        delay = base_delay * (2 ** attempt)
    else:
        delay = base_delay * (attempt + 1)
    
    delay = min(delay, max_delay)
    
    if jitter:
        import random
        delay = delay * (0.5 + random.random() * 0.5)
    
    return delay


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_backoff: bool = True,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
):
    """
    Decorator to retry function calls with exponential backoff.
    
    Args:
        max_attempts: Maximum number of attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries
        exponential_backoff: Use exponential backoff
        jitter: Add random jitter to delays
        exceptions: Tuple of exception types to catch and retry
        on_retry: Optional callback called on each retry (exception, attempt)
        
    Example:
        ```python
        @retry(max_attempts=3, base_delay=1.0, exponential_backoff=True)
        async def fetch_data():
            # Your code here
            pass
        ```
    """
    
    def decorator(func: Callable) -> Callable:
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_attempts - 1:  
                        delay = calculate_backoff(
                            attempt=attempt,
                            base_delay=base_delay,
                            max_delay=max_delay,
                            exponential=exponential_backoff,
                            jitter=jitter,
                        )
                        
                        logger.warning(
                            "retry_attempt",
                            function=func.__name__,
                            attempt=attempt + 1,
                            max_attempts=max_attempts,
                            delay=delay,
                            error=str(e),
                        )
                        
                        if on_retry:
                            on_retry(e, attempt + 1)
                        
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "retry_exhausted",
                            function=func.__name__,
                            max_attempts=max_attempts,
                            error=str(e),
                        )
            
            raise last_exception
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_attempts - 1: 
                        delay = calculate_backoff(
                            attempt=attempt,
                            base_delay=base_delay,
                            max_delay=max_delay,
                            exponential=exponential_backoff,
                            jitter=jitter,
                        )
                        
                        logger.warning(
                            "retry_attempt",
                            function=func.__name__,
                            attempt=attempt + 1,
                            max_attempts=max_attempts,
                            delay=delay,
                            error=str(e),
                        )
                        
                        if on_retry:
                            on_retry(e, attempt + 1)
                        
                        time.sleep(delay)
                    else:
                        logger.error(
                            "retry_exhausted",
                            function=func.__name__,
                            max_attempts=max_attempts,
                            error=str(e),
                        )
            
            raise last_exception
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


async def retry_async(
    func: Callable,
    *args,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_backoff: bool = True,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    **kwargs,
) -> Any:
    """
    Retry an async function call with exponential backoff.
    
    Args:
        func: Async function to call
        *args: Positional arguments for func
        max_attempts: Maximum number of attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries
        exponential_backoff: Use exponential backoff
        jitter: Add random jitter to delays
        exceptions: Tuple of exception types to catch and retry
        **kwargs: Keyword arguments for func
        
    Returns:
        Result of successful function call
        
    Raises:
        Last exception if all attempts fail
    """
    last_exception = None
    
    for attempt in range(max_attempts):
        try:
            return await func(*args, **kwargs)
        
        except exceptions as e:
            last_exception = e
            
            if attempt < max_attempts - 1:
                delay = calculate_backoff(
                    attempt=attempt,
                    base_delay=base_delay,
                    max_delay=max_delay,
                    exponential=exponential_backoff,
                    jitter=jitter,
                )
                
                logger.warning(
                    "retry_attempt",
                    function=func.__name__,
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                    delay=delay,
                    error=str(e),
                )
                
                await asyncio.sleep(delay)
    
    raise last_exception


def retry_sync(
    func: Callable,
    *args,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_backoff: bool = True,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    **kwargs,
) -> Any:
    """
    Retry a sync function call with exponential backoff.
    
    Args:
        func: Function to call
        *args: Positional arguments for func
        max_attempts: Maximum number of attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries
        exponential_backoff: Use exponential backoff
        jitter: Add random jitter to delays
        exceptions: Tuple of exception types to catch and retry
        **kwargs: Keyword arguments for func
        
    Returns:
        Result of successful function call
        
    Raises:
        Last exception if all attempts fail
    """
    last_exception = None
    
    for attempt in range(max_attempts):
        try:
            return func(*args, **kwargs)
        
        except exceptions as e:
            last_exception = e
            
            if attempt < max_attempts - 1:
                delay = calculate_backoff(
                    attempt=attempt,
                    base_delay=base_delay,
                    max_delay=max_delay,
                    exponential=exponential_backoff,
                    jitter=jitter,
                )
                
                logger.warning(
                    "retry_attempt",
                    function=func.__name__,
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                    delay=delay,
                    error=str(e),
                )
                
                time.sleep(delay)
    
    raise last_exception
