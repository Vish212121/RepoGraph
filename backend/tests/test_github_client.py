from app.ingestion.github_client import GitHubClient


def test_next_url_parses_github_link_header() -> None:
    header = '<https://api.github.com/repos/acme/demo/commits?page=2>; rel="next", <https://api.github.com/repos/acme/demo/commits?page=4>; rel="last"'
    assert GitHubClient._next_url(header) == "https://api.github.com/repos/acme/demo/commits?page=2"


def test_next_url_returns_none_without_next_relation() -> None:
    assert GitHubClient._next_url('<https://api.github.com/repos/acme/demo/commits?page=1>; rel="last"') is None

