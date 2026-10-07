from src.providers.openalex import OpenAlexClient


def test_title_search_uses_search_parameter_for_punctuation_safe_queries():
    client = OpenAlexClient()
    client.cache = type(
        "Cache",
        (),
        {"get": lambda self, namespace, key: None, "set": lambda *args, **kwargs: None},
    )()
    requested = []
    client._request_with_retry = lambda url: requested.append(url) or {"results": []}

    client.search_by_title("What Can ResNet Learn Efficiently, Going Beyond Kernels?")

    assert "?filter=title.search:" in requested[0]
    assert "%3F" not in requested[0]
    assert "%2C" not in requested[0]


def test_large_quota_retry_after_fails_over_without_sleeping():
    class Response:
        status_code = 429
        headers = {"Retry-After": "63722"}

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    class Limiter:
        def acquire(self):
            return None

        def is_in_backoff(self):
            return False

    client = OpenAlexClient()
    client.session = Session()
    client._limiter = Limiter()

    assert client._request_with_retry("https://api.openalex.org/works") is None
    assert client.is_available() is False
