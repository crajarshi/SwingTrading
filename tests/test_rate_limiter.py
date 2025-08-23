"""Tests for the token bucket rate limiter."""

import time
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from swingtrading.rate_limiter import TokenBucket


def test_token_bucket_start_empty():
    """Test that token bucket starts empty when configured."""
    bucket = TokenBucket(rate_per_minute=60, start_full=False)
    
    # Should start with 0 tokens
    assert bucket.available() < 1


def test_token_bucket_start_full():
    """Test that token bucket starts full when configured."""
    bucket = TokenBucket(rate_per_minute=60, start_full=True)
    
    # Should start with full capacity
    assert bucket.available() >= 59  # Allow small rounding


def test_token_bucket_refill():
    """Test that tokens refill over time."""
    bucket = TokenBucket(rate_per_minute=60, start_full=False)
    
    # Start with no tokens
    initial = bucket.available()
    
    # Wait a bit
    time.sleep(0.1)
    
    # Should have gained some tokens
    after_wait = bucket.available()
    assert after_wait > initial


def test_token_bucket_acquire_blocks():
    """Test that acquire blocks when no tokens available."""
    bucket = TokenBucket(rate_per_minute=60, start_full=False)
    
    start = time.time()
    bucket.acquire(1)
    elapsed = time.time() - start
    
    # Should have waited for token to become available
    # At 60/min = 1/sec, should wait about 1 second
    assert elapsed >= 0.9  # Allow some tolerance


def test_token_bucket_try_acquire():
    """Test non-blocking try_acquire."""
    bucket = TokenBucket(rate_per_minute=60, start_full=False)
    
    # Should fail when no tokens
    assert bucket.try_acquire(1) == False
    
    # Wait for a token
    time.sleep(1.1)
    
    # Should succeed now
    assert bucket.try_acquire(1) == True


def test_token_bucket_thread_safety():
    """Test that token bucket is thread-safe."""
    bucket = TokenBucket(rate_per_minute=600, start_full=True)  # 10 per second
    
    acquired_count = 0
    lock = threading.Lock()
    
    def acquire_tokens():
        nonlocal acquired_count
        for _ in range(5):
            bucket.acquire(1)
            with lock:
                acquired_count += 1
    
    # Run multiple threads
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(acquire_tokens) for _ in range(4)]
        for future in futures:
            future.result()
    
    # Should have acquired exactly 20 tokens (4 threads * 5 each)
    assert acquired_count == 20


def test_token_bucket_reset():
    """Test that bucket can be reset."""
    bucket = TokenBucket(rate_per_minute=60, start_full=True)
    
    # Use some tokens
    bucket.acquire(10)
    assert bucket.available() < 60
    
    # Reset to empty
    bucket.reset(start_full=False)
    assert bucket.available() < 1
    
    # Reset to full
    bucket.reset(start_full=True)
    assert bucket.available() >= 59


def test_token_bucket_capacity_limit():
    """Test that tokens don't exceed capacity."""
    bucket = TokenBucket(rate_per_minute=60, start_full=True)
    
    # Wait to potentially overfill
    time.sleep(2)
    
    # Should still be at capacity, not more
    assert bucket.available() <= 60