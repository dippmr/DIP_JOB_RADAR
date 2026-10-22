"""Google News RSS searcher."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from html import unescape
from urllib.parse import quote
from xml.etree import ElementTree as ET

import requests

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 2


@dataclass
class SearchResult:
    title: str
    url: str
    description: str
    published: str = ""
    source: str = ""
    query: str = ""  # the search query that found this result
    company: str = ""
    location: str = ""
    apply_url: str = ""
    provider: str = ""
    source_kind: str = "rss"
    external_id: str = ""
    work_mode: str = ""


class GoogleNewsRSS:
    BASE = "https://news.google.com/rss/search"

    def __init__(self, timeout: int = 20, fresh_window: str | None = None):
        self.timeout = timeout
        # Google News time filter: 1h, 1d, 7d, 14d ... (env FRESH_WINDOW)
        if fresh_window is None:
            fresh_window = os.getenv("FRESH_WINDOW", "7d")
        self.fresh_window = fresh_window.strip()
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "DIP-JOB-RADAR/1.0 (public RSS reader)"}
        )

    def _get(self, url: str):
        """GET with a short retry for rate limits and temporary server errors."""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            last_try = attempt == MAX_ATTEMPTS
            try:
                response = self.session.get(url, timeout=self.timeout)
            except (requests.ConnectionError, requests.Timeout):
                if last_try:
                    raise
                time.sleep(BACKOFF_SECONDS * attempt)
                continue

            if response.status_code in RETRY_STATUS and not last_try:
                time.sleep(BACKOFF_SECONDS * attempt)
                continue

            response.raise_for_status()
            return response

    def search(self, query: str, limit: int = 25) -> list[SearchResult]:
        timed_query = (
            f"{query} when:{self.fresh_window}" if self.fresh_window else query
        )
        url = f"{self.BASE}?q={quote(timed_query)}&hl=en-IN&gl=IN&ceid=IN:en"
        root = ET.fromstring(self._get(url).content)

        results = []
        for item in root.findall("./channel/item")[:limit]:
            title = unescape((item.findtext("title") or "").strip())
            link = (item.findtext("link") or "").strip()
            description = unescape(
                re.sub(r"<[^>]+>", " ", item.findtext("description") or "")
            ).strip()
            published = (item.findtext("pubDate") or "").strip()
            source_el = item.find("source")
            source = (source_el.text or "").strip() if source_el is not None else ""

            if title and link:
                results.append(
                    SearchResult(title, link, description, published, source, query)
                )
        return results


def build_queries() -> list[str]:
    """Rotate only UI/UX and product-design leads across target locations.

    Google News RSS is discovery, not confirmation of an employer vacancy.
    ATS verification and India-remote eligibility rules still apply.
    The 48 unique queries form a full circuit across four 12-query runs.
    """
    roles = (
        "UI/UX Designer",
        "UI Designer",
        "UX Designer",
        "Product Designer",
        "Junior UI/UX Designer",
        "Junior Product Designer",
        "Interaction Designer",
        "Associate Product Designer",
    )
    places = (
        '"Ahmedabad"',
        '"Gandhinagar"',
        '("remote India" OR "work from home India")',
    )
    return [f'{place} "{role}" {intent}'
            for place in places for role in roles for intent in ("hiring", "job")]
