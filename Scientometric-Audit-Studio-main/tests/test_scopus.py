from src.providers.scopus import ScopusClient


def test_search_uses_first_author_surname_for_scopus_auth_clause():
    client = ScopusClient(api_key="test-key")
    client.cache = type(
        "Cache",
        (),
        {"get": lambda self, namespace, key: None, "set": lambda *args, **kwargs: None},
    )()
    requested = []
    client._search = lambda query, count=3: requested.append(query) or []

    client.search_by_title_and_author(
        "Parameter-Efficient Transfer Learning for NLP",
        "Neil Houlsby; Andrei Giurgiu",
    )

    assert 'AUTH("Houlsby")' in requested[0]

