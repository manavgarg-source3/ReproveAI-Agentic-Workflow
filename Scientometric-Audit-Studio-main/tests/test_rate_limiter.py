from src.providers.rate_limiter import PoliteRateLimiter


def test_retry_after_is_bounded_for_interactive_analysis():
    limiter = PoliteRateLimiter(
        "registry",
        default_backoff_seconds=2.0,
        max_backoff_seconds=15.0,
    )

    wait = limiter.trigger_backoff("63722")

    assert wait == 15.0

