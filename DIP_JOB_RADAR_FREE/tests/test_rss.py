import pytest
import requests

from search import rss_search
from search.rss_search import GoogleNewsRSS

FEED = b"""<?xml version="1.0"?>
<rss><channel>
  <item>
    <title>UI/UX Designer hiring in Ahmedabad</title>
    <link>https://example.com/a</link>
    <description>&lt;a href="x"&gt;UI/UX Designer&lt;/a&gt; Example News</description>
    <pubDate>Mon, 19 Oct 2026 10:00:00 GMT</pubDate>
    <source url="https://example.com">Example News</source>
  </item>
  <item><title></title><link>https://example.com/empty</link></item>
</channel></rss>"""


class FakeResponse:
    def __init__(self, status_code=200, content=FEED):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(rss_search.time, "sleep", lambda seconds: None)


def make_searcher(responses):
    searcher = GoogleNewsRSS(fresh_window="7d")
    searcher.session = FakeSession(responses)
    return searcher


def test_parses_results_and_remembers_the_query():
    results = make_searcher([FakeResponse()]).search('"Ahmedabad" "UI Designer" hiring')
    assert len(results) == 1  # the item without a title is skipped
    job = results[0]
    assert job.title == "UI/UX Designer hiring in Ahmedabad"
    assert job.source == "Example News"
    assert job.query == '"Ahmedabad" "UI Designer" hiring'
    assert "<a" not in job.description


def test_retries_on_rate_limit_then_succeeds():
    searcher = make_searcher([FakeResponse(429), FakeResponse(200)])
    assert len(searcher.search("q")) == 1
    assert searcher.session.calls == 2


def test_gives_up_after_max_attempts():
    searcher = make_searcher([FakeResponse(429)] * 3)
    with pytest.raises(requests.HTTPError):
        searcher.search("q")
    assert searcher.session.calls == 3


def test_retries_connection_errors():
    searcher = make_searcher([requests.ConnectionError("boom"), FakeResponse()])
    assert len(searcher.search("q")) == 1


def test_does_not_retry_client_errors():
    searcher = make_searcher([FakeResponse(404)])
    with pytest.raises(requests.HTTPError):
        searcher.search("q")
    assert searcher.session.calls == 1
