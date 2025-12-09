"""
Retry logic with exponential backoff and jitter.

Based on best practices from:
- AWS: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
- Python resilience patterns
- Production-tested strategies

Phase 3 M3: Used for autonomous job execution
Phase 3 M4: Used for approval workflows
"""

from __future__ import annotations
import random
import time
import functools
import logging
from typing import Callable, Any, Optional, Tuple, Type
import asyncio

logger = logging.getLogger('cerebric.retry')


def exponential_backoff_retry(
    max_attempts: int = 5,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception, float], None]] = None
):
    """
    Decorator for exponential backoff retry with jitter.
    
    Best Practices:
    - Exponential growth prevents overwhelming servers
    - Jitter prevents thundering herd (synchronized retries)
    - Max delay cap prevents unbounded waits
    - Configurable per task
    
    Args:
        max_attempts: Maximum retry attempts (default: 5)
        base_delay: Initial delay in seconds (default: 0.5)
        max_delay: Maximum delay cap in seconds (default: 30)
        backoff_factor: Exponential growth factor (default: 2.0)
        jitter: Add randomization to prevent synchronized retries (default: True)
        exceptions: Tuple of exceptions to catch (default: all Exception)
        on_retry: Optional callback function(attempt, exception, delay)
    
    Returns:
        Decorated function with retry logic
    
    Example:
        @exponential_backoff_retry(
            max_attempts=3,
            base_delay=1.0,
            max_delay=10.0,
            jitter=True
        )
        def flaky_task():
            # Task that might fail
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            attempt = 0
            last_exception = None
            
            while attempt < max_attempts:
                try:
                    result = func(*args, **kwargs)
                    
                    # Log success after retries
                    if attempt > 0:
                        logger.info(
                            f"Function {func.__name__} succeeded after {attempt} retries"
                        )
                    
                    return result
                
                except exceptions as exc:
                    attempt += 1
                    last_exception = exc
                    
                    if attempt >= max_attempts:
                        logger.error(
                            f"Max retries ({max_attempts}) exceeded for {func.__name__}: {exc}"
                        )
                        raise
                    
                    # Calculate delay: base_delay * (backoff_factor ** (attempt - 1))
                    delay = base_delay * (backoff_factor ** (attempt - 1))
                    delay = min(delay, max_delay)
                    
                    # Add full jitter (randomize between 0 and delay)
                    # This prevents thundering herd when many retries happen simultaneously
                    if jitter:
                        delay = random.uniform(0, delay)
                    
                    logger.warning(
                        f"Retry {attempt}/{max_attempts} for {func.__name__} "
                        f"after {delay:.2f}s delay: {exc}"
                    )
                    
                    # Call retry callback if provided
                    if on_retry:
                        try:
                            on_retry(attempt, exc, delay)
                        except Exception as callback_exc:
                            logger.error(f"Retry callback failed: {callback_exc}")
                    
                    time.sleep(delay)
            
            raise last_exception
        
        return wrapper
    return decorator


def async_exponential_backoff_retry(
    max_attempts: int = 5,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception, float], None]] = None
):
    """
    Async version of exponential backoff retry.
    
    Use this for async functions to avoid blocking event loop.
    
    Args:
        Same as exponential_backoff_retry
    
    Returns:
        Decorated async function with retry logic
    
    Example:
        @async_exponential_backoff_retry(
            max_attempts=3,
            base_delay=1.0
        )
        async def async_flaky_task():
            # Async task that might fail
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            attempt = 0
            last_exception = None
            
            while attempt < max_attempts:
                try:
                    result = await func(*args, **kwargs)
                    
                    if attempt > 0:
                        logger.info(
                            f"Async function {func.__name__} succeeded after {attempt} retries"
                        )
                    
                    return result
                
                except exceptions as exc:
                    attempt += 1
                    last_exception = exc
                    
                    if attempt >= max_attempts:
                        logger.error(
                            f"Max retries ({max_attempts}) exceeded for {func.__name__}: {exc}"
                        )
                        raise
                    
                    delay = base_delay * (backoff_factor ** (attempt - 1))
                    delay = min(delay, max_delay)
                    
                    if jitter:
                        delay = random.uniform(0, delay)
                    
                    logger.warning(
                        f"Retry {attempt}/{max_attempts} for {func.__name__} "
                        f"after {delay:.2f}s delay: {exc}"
                    )
                    
                    if on_retry:
                        try:
                            on_retry(attempt, exc, delay)
                        except Exception as callback_exc:
                            logger.error(f"Retry callback failed: {callback_exc}")
                    
                    await asyncio.sleep(delay)
            
            raise last_exception
        
        return wrapper
    return decorator


class RetryPolicy:
    """
    Configurable retry policy for different task types.
    
    Example:
        # Conservative policy for critical tasks
        critical_policy = RetryPolicy(
            max_attempts=3,
            base_delay=2.0,
            max_delay=60.0
        )
        
        # Aggressive policy for non-critical tasks
        fast_policy = RetryPolicy(
            max_attempts=10,
            base_delay=0.1,
            max_delay=5.0
        )
    """
    
    def __init__(
        self,
        max_attempts: int = 5,
        base_delay: float = 0.5,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0,
        jitter: bool = True,
        exceptions: Tuple[Type[Exception], ...] = (Exception,)
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter
        self.exceptions = exceptions
    
    def retry(self, on_retry: Optional[Callable] = None):
        """Apply this policy as a decorator."""
        return exponential_backoff_retry(
            max_attempts=self.max_attempts,
            base_delay=self.base_delay,
            max_delay=self.max_delay,
            backoff_factor=self.backoff_factor,
            jitter=self.jitter,
            exceptions=self.exceptions,
            on_retry=on_retry
        )
    
    def async_retry(self, on_retry: Optional[Callable] = None):
        """Apply this policy as an async decorator."""
        return async_exponential_backoff_retry(
            max_attempts=self.max_attempts,
            base_delay=self.base_delay,
            max_delay=self.max_delay,
            backoff_factor=self.backoff_factor,
            jitter=self.jitter,
            exceptions=self.exceptions,
            on_retry=on_retry
        )


# Pre-defined policies for common use cases
CRITICAL_TASK_POLICY = RetryPolicy(
    max_attempts=3,
    base_delay=2.0,
    max_delay=60.0,
    backoff_factor=2.0,
    jitter=True
)

STANDARD_TASK_POLICY = RetryPolicy(
    max_attempts=5,
    base_delay=0.5,
    max_delay=30.0,
    backoff_factor=2.0,
    jitter=True
)

FAST_RETRY_POLICY = RetryPolicy(
    max_attempts=10,
    base_delay=0.1,
    max_delay=5.0,
    backoff_factor=1.5,
    jitter=True
)


def retry_with_timeout(
    func: Callable,
    timeout_seconds: float,
    max_attempts: int = 3,
    **retry_kwargs
) -> Any:
    """
    Retry function with overall timeout.
    
    Combines retry logic with timeout enforcement.
    
    Args:
        func: Function to execute
        timeout_seconds: Maximum execution time (all attempts)
        max_attempts: Maximum retry attempts
        **retry_kwargs: Additional retry parameters
    
    Returns:
        Function result
    
    Raises:
        TimeoutError: If overall timeout exceeded
        Exception: If all retries failed
    """
    import signal
    
    class TimeoutException(Exception):
        pass
    
    def timeout_handler(signum, frame):
        raise TimeoutException("Overall timeout exceeded")
    
    # Set timeout
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(int(timeout_seconds))
    
    try:
        # Apply retry decorator
        @exponential_backoff_retry(max_attempts=max_attempts, **retry_kwargs)
        def wrapped_func():
            return func()
        
        result = wrapped_func()
        
        # Cancel timeout
        signal.alarm(0)
        
        return result
    
    except TimeoutException:
        signal.alarm(0)
        raise TimeoutError(f"Function execution exceeded {timeout_seconds}s timeout")
    
    except Exception:
        signal.alarm(0)
        raise
