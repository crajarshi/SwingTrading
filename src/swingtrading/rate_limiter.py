"""Token bucket rate limiter for API request management."""

import threading
import time


class TokenBucket:
    """
    Thread-safe token bucket implementation for rate limiting.
    
    This implementation ensures we don't exceed API rate limits by
    controlling the rate at which requests can be made.
    """
    
    def __init__(self, rate_per_minute: int, start_full: bool = False):
        """
        Initialize the token bucket.
        
        Args:
            rate_per_minute: Maximum requests allowed per minute
            start_full: Whether to start with a full bucket (default: False for safety)
        """
        self.rate = rate_per_minute / 60.0  # Convert to tokens per second
        self.capacity = rate_per_minute
        self.tokens = self.capacity if start_full else 0  # Configurable start state
        self.lock = threading.Lock()
        self.last_update = time.time()
    
    def acquire(self, tokens: int = 1) -> None:
        """
        Acquire tokens from the bucket, blocking if necessary.
        
        This method will block the calling thread until the requested
        number of tokens are available. The lock is released during
        sleep to avoid blocking other threads.
        
        Args:
            tokens: Number of tokens to acquire (default: 1)
        """
        while True:
            # Acquire lock only for token calculation
            with self.lock:
                now = time.time()
                elapsed = now - self.last_update
                
                # Refill tokens based on elapsed time
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last_update = now
                
                # Check if we have enough tokens
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return
                
                # Calculate wait time needed
                wait_time = (tokens - self.tokens) / self.rate
            
            # Sleep OUTSIDE the lock to avoid blocking other threads
            time.sleep(wait_time)
    
    def try_acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens without blocking.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            True if tokens were acquired, False otherwise
        """
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            
            # Refill tokens
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now
            
            # Try to acquire
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            
            return False
    
    def available(self) -> float:
        """
        Get the current number of available tokens.
        
        Returns:
            Number of tokens currently available
        """
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            
            # Calculate current tokens without updating
            return min(self.capacity, self.tokens + elapsed * self.rate)
    
    def reset(self, start_full: bool = False) -> None:
        """
        Reset the bucket to initial state.
        
        Args:
            start_full: Whether to reset to full capacity
        """
        with self.lock:
            self.tokens = self.capacity if start_full else 0
            self.last_update = time.time()