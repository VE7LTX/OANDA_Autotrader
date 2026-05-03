# utils/decorators.py
import time
import logging
import functools
from typing import Callable, Any, Type, Tuple

from .exceptions import OandaApiError, RequestError, RateLimitError # Import relevant exceptions

logger = logging.getLogger(__name__)

def track_latency(func: Callable) -> Callable:
    """Decorator to measure and log the execution time of a function."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            end_time = time.perf_counter()
            duration = (end_time - start_time) * 1000 # Milliseconds
            logger.debug(f"Latency - {func.__name__}: {duration:.2f} ms")
    return wrapper

def retry(
    retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    retry_on_exceptions: Tuple[Type[Exception], ...] = (RequestError, RateLimitError, OandaApiError) # Default retryable exceptions
    # You might want finer control, e.g., only retry on 5xx OandaApiError, not 4xx client errors
) -> Callable:
    """
    Decorator to automatically retry a function call upon specific exceptions.

    Args:
        retries: Maximum number of retry attempts.
        delay: Initial delay between retries in seconds.
        backoff: Multiplier for increasing delay (e.g., 2 means delay doubles each time).
        retry_on_exceptions: A tuple of exception types that trigger a retry.
    """
    if not isinstance(retry_on_exceptions, tuple):
        retry_on_exceptions = (retry_on_exceptions,)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            for attempt in range(retries + 1):
                try:
                    return func(*args, **kwargs)
                except retry_on_exceptions as e:
                    if attempt == retries:
                        logger.error(f"Retry limit exceeded for {func.__name__}. Last error: {e}")
                        raise # Re-raise the last exception
                    else:
                         # Check for specific Retry-After from RateLimitError if needed
                         retry_after_header = None
                         if isinstance(e, RateLimitError) and isinstance(e.error_response, dict):
                              # Placeholder: Adapt if OANDA provides a standard header name for retry delay
                              # retry_after_header = e.error_response.get('headers', {}).get('Retry-After')
                              pass # Add logic here if Retry-After is available

                         actual_delay = float(retry_after_header) if retry_after_header else current_delay

                         logger.warning(f"Retry {attempt + 1}/{retries} for {func.__name__} after error: {e}. Waiting {actual_delay:.2f}s...")
                         time.sleep(actual_delay)
                         current_delay *= backoff # Increase delay for next potential retry
        return wrapper
    return decorator