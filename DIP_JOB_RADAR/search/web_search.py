import os
import requests
from dataclasses import dataclass
from typing import Optional


@dataclass
class SearchResult:
    title: str
    url: str
    description: str = ""
    published: Optional[str] = None
    source: str = ""


class BraveSearch:
    def __init__(self, api_key: str, api_url: str | None = None):
        self.api_key = api_key
        self.api_url = api_url or "https://api.search.brave.com/res/v1/web/search"

    def search(self, query: str, count: int = 10) -> list[SearchResult]:
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        params = {
            "q": query,
            "count": count,
            "country": "IN",
            "search_lang": "en",
            "safesearch": "moderate"
        }

        response = requests.get(
            self.api_url,
            headers=headers,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        results = []
        for item in payload.get("web", {}).get("results", []):
            results.append(
                SearchResult(
                    title=(item.get("title") or "").strip(),
                    url=(item.get("url") or "").strip(),
                    description=(item.get("description") or "").strip(),
                    published=item.get("page_age") or item.get("age"),
                    source=self._domain(item.get("url", "")),
                )
            )
        return results

    @staticmethod
    def _domain(url: str) -> str:
        from urllib.parse import urlparse
        return urlparse(url).netloc.lower().replace("www.", "")


def build_search_queries(keywords: dict) -> list[str]:
    location = '"Ahmedabad"'
    roles = keywords["primary_roles"]
    bridges = keywords["bridge_roles"]
    hiring = keywords["hiring_signals"]
    skills = keywords["skills"]

    queries = []

    # High-intent role searches.
    for role in roles[:8]:
        queries.append(f'{location} "{role}" hiring')
        queries.append(f'{location} "{role}" job')
        queries.append(f'{location} "{role}" Figma')

    # Recruiter/social-style searches.
    for phrase in [
        '"we\'re hiring" designer',
        '"we are hiring" designer',
        '"looking for" designer',
        '"join our team" designer',
        '"designer required"'
    ]:
        queries.append(f'{location} {phrase}')

    # Bridge roles.
    for role in bridges:
        queries.append(f'{location} "{role}"')

    # Skill combinations catch posts whose title is vague.
    for skill in ["Figma", "product design", "UI design", "UX design", "design system"]:
        queries.append(f'{location} {skill} designer hiring')

    # Public LinkedIn posts/pages.
    for role in roles[:7]:
        queries.append(f'site:linkedin.com/posts {location} "{role}" hiring')
        queries.append(f'site:linkedin.com/posts {location} "{role}"')
    queries.append(f'site:linkedin.com/posts {location} designer "looking for"')

    # Public job-board pages.
    for domain in keywords["search_domains"]:
        queries.append(f'site:{domain} {location} "UI/UX Designer"')
        queries.append(f'site:{domain} {location} "Product Designer"')
        queries.append(f'site:{domain} {location} "UI Designer"')

    # Keep API usage predictable.
    deduped = []
    seen = set()
    for q in queries:
        q = " ".join(q.split())
        if q not in seen:
            seen.add(q)
            deduped.append(q)
    return deduped
