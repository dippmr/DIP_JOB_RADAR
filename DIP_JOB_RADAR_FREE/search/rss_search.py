from __future__ import annotations
from dataclasses import dataclass
from html import unescape
from urllib.parse import quote
from xml.etree import ElementTree as ET
import re
import requests

@dataclass
class SearchResult:
    title: str
    url: str
    description: str
    published: str = ""
    source: str = ""

class GoogleNewsRSS:
    BASE = "https://news.google.com/rss/search"
    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "DIP-JOB-RADAR/1.0 (public RSS reader)"})
    def search(self, query: str, limit: int = 25) -> list[SearchResult]:
        url = f"{self.BASE}?q={quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        out = []
        for item in root.findall("./channel/item")[:limit]:
            title = unescape((item.findtext("title") or "").strip())
            link = (item.findtext("link") or "").strip()
            description = unescape(re.sub(r"<[^>]+>", " ", item.findtext("description") or "")).strip()
            published = (item.findtext("pubDate") or "").strip()
            source_el = item.find("source")
            source = (source_el.text or "").strip() if source_el is not None else ""
            if title and link:
                out.append(SearchResult(title, link, description, published, source))
        return out

def build_queries() -> list[str]:
    roles = ["UI Designer", "UI/UX Designer", "Junior UI/UX Designer", "Visual Designer", "Interaction Designer", "Junior Product Designer", "Associate Product Designer", "Product Designer", "Graphic Designer UI UX", "Graphic and UI UX Designer"]
    queries = []
    for role in roles:
        queries += [f'"Ahmedabad" "{role}" hiring', f'"Ahmedabad" "{role}" job', f'"Ahmedabad" "{role}" Figma']
    queries += [
        '"Ahmedabad" "we are hiring" designer', '"Ahmedabad" "we\'re hiring" designer',
        '"Ahmedabad" "looking for" designer', '"Ahmedabad" "designer required"',
        '"Ahmedabad" "join our team" designer', '"Ahmedabad" designer Figma hiring',
        '"Ahmedabad" UI UX hiring', '"Ahmedabad" product designer hiring',
        '"Ahmedabad" site:linkedin.com/posts designer hiring',
        '"Ahmedabad" site:linkedin.com/posts "UI/UX Designer"',
        '"Ahmedabad" site:linkedin.com/posts "Product Designer"',
        '"Ahmedabad" site:linkedin.com/posts "Visual Designer"',
        '"Ahmedabad" site:naukri.com UI UX designer',
        '"Ahmedabad" site:indeed.com UI UX designer',
        '"Ahmedabad" site:foundit.in UI UX designer',
        '"Ahmedabad" site:wellfound.com product designer'
    ]
    return list(dict.fromkeys(queries))
