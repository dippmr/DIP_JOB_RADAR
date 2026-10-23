"""Read configured PUBLIC employer career pages (never social networks).

Strict mode: a role-specific same-site page containing the actual role,
location and hiring/application evidence can become a verified career job.
Generic careers indexes become unverified REVIEW LEADS only. No claims of
freshness: the fetch confirms current page content, not original posting date.
"""
from __future__ import annotations

import ipaddress
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit

import requests

from radar.verification import role_groups
from search.post_parser import HIRING
from search.rss_search import SearchResult

MAX_BYTES = 350_000
DEFAULT_TIMEOUT = 12


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "svg", "noscript", "template"):
            self.hidden += 1
        elif tag in ("p", "li", "h1", "h2", "h3", "section", "br", "div") and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "svg", "noscript", "template"):
            self.hidden = max(0, self.hidden - 1)
        elif tag in ("p", "li", "h1", "h2", "h3", "section", "div") and not self.hidden:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

    def text(self):
        return re.sub(r"\n\s*\n+", "\n", re.sub(r"[\t\r ]+", " ", "".join(self.parts))).strip()


def secure_public_url(url):
    """Only ordinary public HTTPS domain URLs from explicit configuration."""
    try:
        p = urlsplit(url)
        host = p.hostname or ""
        if p.scheme != "https" or not host or p.username or p.password or p.port not in (None, 443):
            return False
        if host == "localhost" or not ("." in host) or host.endswith((".local", ".internal")):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            return True
    except ValueError:
        return False


def download_page(url, session=None, timeout=DEFAULT_TIMEOUT):
    if not secure_public_url(url):
        raise ValueError("Invalid public HTTPS career URL")
    session = session or requests.Session()
    response = session.get(url, timeout=timeout, allow_redirects=False,
                           headers={"User-Agent": "DIP-JOB-RADAR/3.0 (public careers checker)",
                                    "Accept": "text/html"}, stream=True)
    try:
        response.raise_for_status()
        if response.is_redirect:
            raise ValueError("Redirect skipped: update configured career URL")
        if "text/html" not in response.headers.get("Content-Type", "text/html").lower():
            raise ValueError("Career URL did not return HTML")
        length = int(response.headers.get("Content-Length", "0") or "0")
        if length > MAX_BYTES:
            raise ValueError("Career HTML too large")
        data = b""
        for chunk in response.iter_content(8192):
            data += chunk
            if len(data) > MAX_BYTES:
                raise ValueError("Career HTML too large")
        parser = VisibleText()
        parser.feed(data.decode(response.encoding or "utf-8", errors="replace"))
        return parser.text()[:20000]
    finally:
        response.close()


def page_candidate(page, text):
    """Only materialize a role that is literally present on the live page."""
    title = page.get("title", "").strip()
    expected = role_groups(title)
    index_hiring = bool(re.search(r"\b(?:roles?\s+we\s+hire|open\s+positions?|"
                                  r"vacancies|apply(?:\s+now)?)\b", text, re.I))
    if not expected or not (HIRING.search(text) or index_hiring):
        return None
    # Do not accept config title by itself as live evidence.
    known_patterns = [
        re.compile(r"\b" + re.escape(title).replace(r"\ ", r"\s+") + r"(?!\w)", re.I),
    ]
    if not any(pattern.search(text) for pattern in known_patterns):
        return None
    company = page.get("company", "").strip()
    url = page.get("url", "").strip()
    if not company or not secure_public_url(url):
        return None
    # The location must be present on the actual employer page, not merely the
    # watchlist config. Avoid extrapolating a company HQ to a vacancy.
    location = ""
    for city in ("Ahmedabad", "Gandhinagar"):
        if re.search(r"\b" + city + r"\b", text, re.I):
            location = city
            break
    if not location and re.search(r"\bremote\b.{0,35}\bIndia\b|\bIndia\b.{0,35}\bremote\b", text, re.I | re.S):
        location = "Remote - India"
    # Vacancy-specific URL plus explicit hiring language. General index pages
    # are not independently verified individual jobs.
    path = urlsplit(url).path.rstrip("/").lower()
    is_detail = bool(re.search(r"/(?:career|careers|jobs|job|openings|jobs-opening)/[^/]+$", path))
    # An arbitrary role-specific URL alone is not proof of an open vacancy.
    apply_evidence = bool(re.search(r"\b(?:apply\s+(?:now|for|here)|send\s+your\s+(?:cv|resume)|"
                                    r"we\s+are\s+(?:hiring|looking\s+for)|we(?:'|’)?re\s+hiring)\b", text, re.I))
    role_slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
    url_slug = path.rsplit("/", 1)[-1]
    normalized_slug = role_slug.replace("ux-ui", "ui-ux")
    url_normalized = url_slug.replace("ux-ui", "ui-ux")
    slug_matches = url_normalized in {normalized_slug,
                                     normalized_slug.replace("junior-", "jr-", 1),
                                     normalized_slug.replace("senior-", "sr-", 1)}
    # Exact role URL prevents sidebar or related-role mentions from being
    # mistaken for the principal vacancy described by the page.
    verified = is_detail and slug_matches and apply_evidence and bool(location)
    return SearchResult(
        title=title, url=url,
        description=text[:5000] if verified else text[:1500],
        company=company, location=location,
        source=f"Employer career page · {company}",
        source_kind="career" if verified else "career_lead",
        apply_url=url if verified else "",
        published="",  # fetch time is not posting time
        external_id="",
    )


def fetch_career_pages(pages, *, session=None, timeout=DEFAULT_TIMEOUT):
    """Return (candidates, successes, failures), one result per configured page."""
    results, successes, failures = [], 0, []
    for page in pages:
        try:
            text = download_page(page["url"], session=session, timeout=timeout)
            successes += 1
            candidate = page_candidate(page, text)
            if candidate:
                results.append(candidate)
        except (requests.RequestException, UnicodeError, ValueError, KeyError) as error:
            failures.append((page.get("company", "unknown"), type(error).__name__))
    return results, successes, failures
