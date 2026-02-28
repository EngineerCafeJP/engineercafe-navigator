"""Tests for rate_limit utility (#120)"""

from backend.utils.rate_limit import rate_limit


def test_rate_limit_returns_callable():
    """rate_limit should return a decorator (callable)"""
    decorator = rate_limit("10/minute")
    assert callable(decorator)


def test_rate_limit_noop_preserves_function():
    """When slowapi is not installed, decorator should be a no-op"""

    @rate_limit("10/minute")
    def dummy():
        return "ok"

    # No-op decorator should not wrap the function
    assert dummy() == "ok"


def test_rate_limit_different_limits():
    """Different rate limit strings should all return valid decorators"""
    for limit_str in ["60/minute", "30/minute", "10/minute", "5/minute"]:
        decorator = rate_limit(limit_str)
        assert callable(decorator)
