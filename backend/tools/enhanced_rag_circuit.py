"""Circuit breaker state for enhanced RAG search."""

import time
from typing import Optional


class CircuitBreaker:
    """Simple circuit breaker to prevent cascading RAG/LLM failures."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._state = "closed"  # closed, open, half_open

    @property
    def is_open(self) -> bool:
        if self._state == "open":
            if (
                self._last_failure_time
                and (time.time() - self._last_failure_time) > self.recovery_timeout
            ):
                self._state = "half_open"
                return False
            return True
        return False

    def record_success(self):
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            self._state = "open"

    def reset(self):
        """Reset circuit breaker to closed state (useful for testing)."""
        self._failure_count = 0
        self._last_failure_time = None
        self._state = "closed"


_rag_circuit_breaker = CircuitBreaker()
