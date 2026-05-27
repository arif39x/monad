from __future__ import annotations

from sandbox.security import NetworkPolicy, RateLimiter


def test_rate_limiter_allows_first_request() -> None:
    limiter = RateLimiter(max_per_minute=60, burst=10)
    assert limiter.check("test") is True


def test_rate_limiter_exhausted() -> None:
    limiter = RateLimiter(max_per_minute=1, burst=1)
    assert limiter.check("test") is True
    assert limiter.check("test") is False


def test_rate_limiter_burst() -> None:
    limiter = RateLimiter(max_per_minute=60, burst=5)
    for _ in range(5):
        assert limiter.check("burst") is True
    # after burst exhausted, rate limiting kicks in
    assert limiter.check("burst") is False


def test_rate_limiter_separate_keys() -> None:
    limiter = RateLimiter(max_per_minute=1, burst=1)
    assert limiter.check("key_a") is True
    assert limiter.check("key_a") is False
    assert limiter.check("key_b") is True


def test_network_policy_disabled() -> None:
    policy = NetworkPolicy(enabled=False)
    assert policy.check_egress(["curl", "http://evil.com"]) is True


def test_network_policy_blocked() -> None:
    policy = NetworkPolicy(enabled=True, allowed_hosts=["api.openai.com"])
    assert policy.check_egress(["curl", "http://evil.com"]) is False


def test_network_policy_allowed() -> None:
    policy = NetworkPolicy(enabled=True, allowed_hosts=["api.openai.com"])
    assert policy.check_egress(["curl", "https://api.openai.com/v1/chat"]) is True


def test_network_policy_non_network_command() -> None:
    policy = NetworkPolicy(enabled=True, allowed_hosts=[])
    assert policy.check_egress(["ls", "-la"]) is True


def test_network_policy_subdomain_allowed() -> None:
    policy = NetworkPolicy(enabled=True, allowed_hosts=["openai.com"])
    assert policy.check_egress(["curl", "https://api.openai.com/v1"]) is True


def test_network_policy_empty_command() -> None:
    policy = NetworkPolicy(enabled=True)
    assert policy.check_egress([]) is True
