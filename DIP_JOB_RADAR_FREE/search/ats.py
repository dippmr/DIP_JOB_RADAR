"""Public ATS board adapters. No job-site scraping or application submission."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from html import unescape
from urllib.parse import quote, urlsplit

import requests

from search.rss_search import SearchResult

ALLOWED_PROVIDERS = {"greenhouse", "lever", "ashby"}
TOKEN_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{2,90}$")


def clean_html(value):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]*>", " ", str(value or "")))).strip()[:5500]


def safe_link(url):
    """Only allow actual https URLs; reject pseudo-links."""
    try:
        p = urlsplit(url)
        return url if p.scheme == "https" and p.netloc and not p.username else ""
    except (ValueError, TypeError):
        return ""


def _date(value):
    """Epoch ms and ISO timestamps supported; never confuse updated_at with posted_at."""
    if not value:
        return ""
    try:
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value / 1000 if value > 10**11 else value, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
    except (TypeError, ValueError, OverflowError):
        return ""


def parse_greenhouse(data, company, token):
    for item in data.get("jobs", []):
        title = item.get("title") or ""
        apply_url = safe_link(item.get("absolute_url", ""))
        if not title or not apply_url:
            continue
        location = (item.get("location") or {}).get("name", "")
        yield SearchResult(
            title=title, url=apply_url, description=clean_html(item.get("content", "")),
            company=company, source=f"Greenhouse · {company}", source_kind="ats",
            provider="greenhouse", location=location, apply_url=apply_url,
            external_id=f"greenhouse:{token}:{item.get('id')}",
            # Greenhouse updated_at is NOT a first-posted date.
        )


def parse_lever(data, company, token):
    for item in data if isinstance(data, list) else []:
        title = item.get("text", "")
        apply_url = safe_link(item.get("applyUrl", ""))
        detail_url = safe_link(item.get("hostedUrl", "")) or apply_url
        if not title or not detail_url:
            continue
        cats = item.get("categories") or {}
        locations = cats.get("allLocations") or []
        location = ", ".join(locations) if locations else cats.get("location", "")
        yield SearchResult(
            title=title, url=detail_url,
            description=clean_html(item.get("descriptionPlain") or item.get("description", "")),
            company=company, source=f"Lever · {company}", source_kind="ats", provider="lever",
            location=location, apply_url=apply_url or detail_url,
            external_id=f"lever:{token}:{item.get('id')}",
            published=_date(item.get("createdAt")),
        )


def parse_ashby(data, company, token):
    for item in data.get("jobs", []):
        if item.get("isListed") is False:
            continue
        title = item.get("title", "")
        detail_url = safe_link(item.get("jobUrl", ""))
        apply_url = safe_link(item.get("applyUrl", "")) or detail_url
        if not title or not detail_url:
            continue
        locations = [item.get("location", "")]
        locations += [x.get("location", "") for x in item.get("secondaryLocations", [])]
        yield SearchResult(
            title=title, url=detail_url,
            description=clean_html(item.get("descriptionPlain") or item.get("descriptionHtml") or ""),
            company=company, source=f"Ashby · {company}", source_kind="ats", provider="ashby",
            location=", ".join(filter(None, locations)), apply_url=apply_url,
            external_id=f"ashby:{token}:{item.get('id') or detail_url.rsplit('/', 1)[-1]}",
            published=_date(item.get("publishedAt")),
        )


def board_url(provider, token, region="global"):
    if provider not in ALLOWED_PROVIDERS or not TOKEN_PATTERN.fullmatch(token):
        raise ValueError("Invalid ATS provider or board token")
    board = quote(token, safe="")
    if provider == "greenhouse":
        return f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    if provider == "ashby":
        return f"https://api.ashbyhq.com/posting-api/job-board/{board}"
    if region not in ("global", "eu"):
        raise ValueError("Lever region must be global or eu")
    domain = "api.eu.lever.co" if region == "eu" else "api.lever.co"
    return f"https://{domain}/v0/postings/{board}?mode=json&limit=100"


def _get_json(session, url, timeout):
    for attempt in range(3):
        try:
            r = session.get(url, timeout=timeout, headers={"Accept": "application/json"})
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                continue
            r.raise_for_status()
            return r.json()
        except (requests.ConnectionError, requests.Timeout):
            if attempt == 2:
                raise
    raise RuntimeError("ATS temporarily unavailable")


def fetch_board(board, session=None, timeout=15):
    provider = board["provider"].lower()
    token = board["token"].strip()
    company = board["company"].strip()
    session = session or requests.Session()
    data = _get_json(session, board_url(provider, token, board.get("region", "global")), timeout)
    if provider == "greenhouse":
        return list(parse_greenhouse(data, company, token))
    if provider == "ashby":
        return list(parse_ashby(data, company, token))
    # Lever supports pagination. Retrieve the remaining pages if exactly 100 returned.
    out = list(parse_lever(data, company, token))
    skip = 100
    while isinstance(data, list) and len(data) == 100 and skip < 1000:
        url = board_url(provider, token, board.get("region", "global")) + f"&skip={skip}"
        data = _get_json(session, url, timeout)
        out.extend(parse_lever(data, company, token))
        skip += 100
    return out
