"""
Tests for retry logic with exponential backoff.

Phase 3 M3: Test retry mechanisms for autonomous execution
"""

import pytest
import time
from cerebric_core.utils.retry import (
    exponential_backoff_retry,
    RetryPolicy,
    CRITICAL_TASK_POLICY,
    STANDARD_TASK_POLICY,
    FAST_RETRY_POLICY
)


class TestExponentialBackoffRetry:
    """Test exponential backoff retry decorator."""
    
    def test_success_on_first_attempt(self):
        """Test function succeeds on first attempt."""
        call_count = 0
        
        @exponential_backoff_retry(max_attempts=3)
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = successful_func()
        assert result == "success"
        assert call_count == 1
    
    def test_success_after_retries(self):
        """Test function succeeds after some failures."""
        call_count = 0
        
        @exponential_backoff_retry(
            max_attempts=5,
            base_delay=0.01,  # Short delay for testing
            jitter=False  # Predictable for testing
        )
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return "success"
        
        result = flaky_func()
        assert result == "success"
        assert call_count == 3  # Failed twice, succeeded on third
    
    def test_max_attempts_exceeded(self):
        """Test function fails after max attempts."""
        call_count = 0
        
        @exponential_backoff_retry(
            max_attempts=3,
            base_delay=0.01,
            jitter=False
        )
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")
        
        with pytest.raises(ValueError, match="Always fails"):
            always_fails()
        
        assert call_count == 3  # Tried 3 times
    
    def test_exponential_delay_growth(self):
        """Test delay grows exponentially."""
        delays = []
        
        def on_retry_callback(attempt, exc, delay):
            delays.append(delay)
        
        call_count = 0
        
        @exponential_backoff_retry(
            max_attempts=4,
            base_delay=1.0,
            backoff_factor=2.0,
            jitter=False,  # No jitter for predictable delays
            on_retry=on_retry_callback
        )
        def failing_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Fail")
        
        with pytest.raises(ValueError):
            failing_func()
        
        # Delays should be: 1.0, 2.0, 4.0
        assert len(delays) == 3
        assert delays[0] == pytest.approx(1.0, rel=0.01)
        assert delays[1] == pytest.approx(2.0, rel=0.01)
        assert delays[2] == pytest.approx(4.0, rel=0.01)
    
    def test_max_delay_cap(self):
        """Test delay is capped at max_delay."""
        delays = []
        
        def on_retry_callback(attempt, exc, delay):
            delays.append(delay)
        
        @exponential_backoff_retry(
            max_attempts=5,
            base_delay=10.0,
            max_delay=15.0,
            backoff_factor=2.0,
            jitter=False,
            on_retry=on_retry_callback
        )
        def failing_func():
            raise ValueError("Fail")
        
        with pytest.raises(ValueError):
            failing_func()
        
        # All delays should be capped at 15.0
        for delay in delays:
            assert delay <= 15.0
    
    def test_jitter_adds_randomness(self):
        """Test jitter randomizes delays."""
        delays = []
        
        def on_retry_callback(attempt, exc, delay):
            delays.append(delay)
        
        call_count = 0
        
        @exponential_backoff_retry(
            max_attempts=10,
            base_delay=1.0,
            backoff_factor=2.0,
            jitter=True,
            on_retry=on_retry_callback
        )
        def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count < 10:
                raise ValueError("Fail")
            return "success"
        
        result = failing_func()
        
        # With jitter, delays should vary
        # Check that not all delays are identical
        assert len(set(delays)) > 1  # At least some variation
        
        # All delays should be between 0 and their theoretical max
        for i, delay in enumerate(delays):
            max_expected = 1.0 * (2.0 ** i)
            assert 0 <= delay <= max_expected
    
    def test_specific_exceptions(self):
        """Test retry only on specific exceptions."""
        call_count = 0
        
        @exponential_backoff_retry(
            max_attempts=3,
            base_delay=0.01,
            exceptions=(ValueError,)  # Only retry on ValueError
        )
        def mixed_exceptions():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Retry this")
            elif call_count == 2:
                raise TypeError("Don't retry this")
        
        # Should not retry on TypeError
        with pytest.raises(TypeError, match="Don't retry this"):
            mixed_exceptions()
        
        assert call_count == 2  # First attempt + one retry


class TestRetryPolicy:
    """Test pre-configured retry policies."""
    
    def test_critical_task_policy(self):
        """Test critical task policy is conservative."""
        assert CRITICAL_TASK_POLICY.max_attempts == 3
        assert CRITICAL_TASK_POLICY.base_delay >= 2.0
        assert CRITICAL_TASK_POLICY.max_delay >= 60.0
    
    def test_standard_task_policy(self):
        """Test standard task policy is balanced."""
        assert STANDARD_TASK_POLICY.max_attempts == 5
        assert STANDARD_TASK_POLICY.base_delay == pytest.approx(0.5)
        assert STANDARD_TASK_POLICY.max_delay == pytest.approx(30.0)
    
    def test_fast_retry_policy(self):
        """Test fast retry policy allows more attempts with shorter delays."""
        assert FAST_RETRY_POLICY.max_attempts >= 10
        assert FAST_RETRY_POLICY.base_delay <= 0.1
        assert FAST_RETRY_POLICY.max_delay <= 5.0
    
    def test_custom_policy(self):
        """Test creating custom retry policy."""
        custom_policy = RetryPolicy(
            max_attempts=2,
            base_delay=0.5,
            max_delay=5.0,
            backoff_factor=3.0,
            jitter=False
        )
        
        call_count = 0
        
        @custom_policy.retry()
        def custom_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Fail once")
            return "success"
        
        result = custom_func()
        assert result == "success"
        assert call_count == 2


class TestRetryCallbacks:
    """Test retry callback functionality."""
    
    def test_on_retry_callback_called(self):
        """Test callback is called on each retry."""
        callback_calls = []
        
        def on_retry(attempt, exc, delay):
            callback_calls.append({
                'attempt': attempt,
                'exception': str(exc),
                'delay': delay
            })
        
        call_count = 0
        
        @exponential_backoff_retry(
            max_attempts=3,
            base_delay=0.01,
            jitter=False,
            on_retry=on_retry
        )
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"Fail {call_count}")
            return "success"
        
        result = flaky_func()
        
        # Should have 2 callback calls (2 retries before success)
        assert len(callback_calls) == 2
        assert callback_calls[0]['attempt'] == 1
        assert callback_calls[1]['attempt'] == 2
    
    def test_callback_exception_doesnt_break_retry(self):
        """Test callback exceptions don't break retry logic."""
        def bad_callback(attempt, exc, delay):
            raise RuntimeError("Callback failed")
        
        call_count = 0
        
        @exponential_backoff_retry(
            max_attempts=3,
            base_delay=0.01,
            on_retry=bad_callback
        )
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Fail")
            return "success"
        
        # Should still succeed despite callback failures
        result = flaky_func()
        assert result == "success"
        assert call_count == 3


class TestRetryPerformance:
    """Test retry performance characteristics."""
    
    def test_retry_timing(self):
        """Test actual retry delays match expected values."""
        start_time = time.time()
        
        call_count = 0
        
        @exponential_backoff_retry(
            max_attempts=3,
            base_delay=0.1,
            backoff_factor=2.0,
            jitter=False  # No jitter for predictable timing
        )
        def timed_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Fail")
            return "success"
        
        result = timed_func()
        elapsed = time.time() - start_time
        
        # Expected delays: 0.1 + 0.2 = 0.3 seconds
        # Allow 20% tolerance for test flakiness
        assert 0.25 <= elapsed <= 0.40
    
    def test_no_delay_on_success(self):
        """Test no delay when function succeeds immediately."""
        start_time = time.time()
        
        @exponential_backoff_retry(max_attempts=3, base_delay=1.0)
        def immediate_success():
            return "success"
        
        result = immediate_success()
        elapsed = time.time() - start_time
        
        # Should complete almost instantly (no retries)
        assert elapsed < 0.1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
