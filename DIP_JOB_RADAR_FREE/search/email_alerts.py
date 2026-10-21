"""Optional read-only IMAP importer for official job-alert emails.

Does not scrape job boards, follow email tracking redirects, or mark emails read.
Extracted links are UNVERIFIED leads, not employer-confirmed vacancies.
Only individual-job URLs on eight recognized platforms are accepted.
"""
from __future__ import annotations

import email
import imaplib
import os
import re
import ssl
from datetime import datetime, timedelta, timezone
from email import policy
from email.message import Message
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit, urlunsplit

from search.rss_search import SearchResult

# Exact domain/subdomain boundaries are checked; example.com.evil.tld is rejected.
PLATFORM_DOMAINS = {
    "LinkedIn": ("linkedin.com",),
    "Naukri": ("naukri.com",),
    "Indeed": ("indeed.com",),
    "Apna": ("apna.co",),
    "Internshala": ("internshala.com",),
    "Wellfound": ("wellfound.com",),
    "Cutshort": ("cutshort.io",),
    "Behance": ("behance.net",),
}

ROLE_TITLE = re.compile(
    r"\b(?:graphic|graphics|visual|product|ui\s*[/+&-]?\s*ux|ux\s*[/+&-]?\s*ui|ui|ux|"
    r"user experience|user interface|interaction|brand|creative|web|digital)\s+"
    r"(?:design(?:er|ers)?|design\s+specialist)\b", re.I
)
MAX_MESSAGE_BYTES = 750_000
MAX_LINKS_PER_EMAIL = 35
MAX_LEADS_PER_RUN = 100


def _hostname_allowed(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def individual_job_url(raw_url: str) -> tuple[str, str] | None:
    """Return (platform, sanitized direct link), or None for unsafe/ambiguous links.

    Tracking parameters are stripped before storing URLs in a PUBLIC repo DB.
    No redirect destinations are fetched or guessed.
    """
    raw_url = unescape((raw_url or "").strip())
    if len(raw_url) > 2500:
        return None
    try:
        p = urlsplit(raw_url)
        if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
            return None
        host = p.hostname.lower()
        platform = next((name for name, domains in PLATFORM_DOMAINS.items()
                         if any(_hostname_allowed(host, domain) for domain in domains)), None)
        if not platform:
            return None
        path = p.path or "/"
        q = parse_qs(p.query)
        params = ""
        valid = False
        if platform == "LinkedIn":
            valid = bool(re.search(r"/(?:comm/)?jobs/view/\d{5,}(?:/|$)", path))
        elif platform == "Naukri":
            valid = "job-listings-" in path.lower() or bool(re.search(r"/job-listing/\d+", path))
        elif platform == "Indeed":
            if path.rstrip("/") == "/viewjob" and q.get("jk") and re.fullmatch(r"[A-Za-z0-9]{8,32}", q["jk"][0]):
                valid, params = True, "jk=" + q["jk"][0]
        elif platform == "Apna":
            valid = bool(re.search(r"/job/[^/]{5,}", path))
        elif platform == "Internshala":
            valid = path.startswith(("/internship/detail/", "/job/detail/", "/jobs/detail/"))
        elif platform == "Wellfound":
            valid = bool(re.search(r"/jobs/\d+", path))
        elif platform == "Cutshort":
            valid = bool(re.search(r"/job/[^/]{5,}", path))
        elif platform == "Behance":
            valid = bool(re.search(r"/joblist/[^/]{3,}", path))
        if not valid:
            return None
        clean = urlunsplit(("https", host, path.rstrip("/"), params, ""))
        return platform, clean
    except (ValueError, TypeError):
        return None


class _AlertHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.entries: list[dict[str, str]] = []
        self._anchor: dict[str, str] | None = None
        self._after: dict[str, str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._after = None
            href = dict(attrs).get("href", "")
            self._anchor = {"url": href, "title": "", "context": ""}
        elif tag in ("script", "style"):
            self._after = None

    def handle_endtag(self, tag):
        if tag == "a" and self._anchor:
            self.entries.append(self._anchor)
            self._after = self._anchor
            self._anchor = None
        elif tag in ("tr", "li", "table", "section"):
            self._after = None

    def handle_data(self, data):
        normalized = re.sub(r"\s+", " ", data).strip()
        if not normalized:
            return
        if self._anchor is not None:
            self._anchor["title"] += " " + normalized
        elif self._after is not None and len(self._after["context"]) < 130:
            self._after["context"] += " " + normalized


def _text_parts(message: Message) -> tuple[str, str]:
    plain, html = [], []
    for part in message.walk():
        if part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() not in ("text/plain", "text/html"):
            continue
        try:
            body = part.get_content()
        except (UnicodeError, LookupError, ValueError, TypeError):
            continue
        if not isinstance(body, str):
            continue
        if part.get_content_type() == "text/html":
            html.append(body[:200_000])
        else:
            plain.append(body[:100_000])
    return "\n".join(plain), "\n".join(html)


def _location_hint(text: str) -> str:
    """Only short, near-link context. Never infer the reader's country from a search query."""
    short = text[:135]
    for phrase in ("Ahmedabad", "Gandhinagar"):
        if re.search(r"\b" + phrase + r"\b", short, re.I):
            return phrase
    if re.search(r"\bremote\b.{0,30}\bIndia\b|\bIndia\b.{0,30}\bremote\b", short, re.I):
        return "Remote - India"
    return ""


def parse_alert_message(raw_message: bytes, *, max_age_days: int = 7) -> list[SearchResult]:
    """Parse label-linked jobs only; never interpret an email digest as a verified employer posting."""
    if not raw_message or len(raw_message) > MAX_MESSAGE_BYTES:
        return []
    msg = email.message_from_bytes(raw_message, policy=policy.default)
    # A message's Date is the *alert email timestamp*, not the job publication date.
    try:
        sent = parsedate_to_datetime(msg.get("Date", ""))
        if sent.tzinfo is None:
            sent = sent.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if sent > now + timedelta(days=1) or sent < now - timedelta(days=max_age_days):
            return []
    except (TypeError, ValueError, OverflowError):
        return []
    plain, html = _text_parts(msg)
    matches: list[dict[str, str]] = []
    if html:
        parser = _AlertHTML()
        parser.feed(html)
        matches = parser.entries
    else:
        # Simple text alerts: Job Title — Location followed by a direct URL.
        lines = [line.strip() for line in plain.splitlines()]
        for index, line in enumerate(lines):
            url = re.search(r"https://[^\s<>\"']+", line)
            if not url:
                continue
            previous = lines[index-1] if index else ""
            matches.append({"url": url.group(0), "title": previous, "context": line[:135]})
    jobs: list[SearchResult] = []
    visited: set[str] = set()
    for match in matches[:MAX_LINKS_PER_EMAIL]:
        platform_link = individual_job_url(match.get("url", ""))
        if not platform_link:
            continue
        platform, url = platform_link
        title = re.sub(r"\s+", " ", unescape(match.get("title", ""))).strip()[:130]
        if not ROLE_TITLE.search(title) or url in visited:
            continue
        visited.add(url)
        vicinity = re.sub(r"\s+", " ", match.get("context", "")).strip()[:135]
        # Never put entire personal emails in the PUBLIC SQLite database.
        jobs.append(SearchResult(
            title=title, url=url, description=("Location stated near email link: " + _location_hint(title + " " + vicinity)) if _location_hint(title + " " + vicinity) else "",
            published="",  # email receipt timestamp is not job-posted timestamp
            source=f"{platform} · email alert (unverified)",
            company="", location=_location_hint(title + " " + vicinity),
            apply_url="", provider=platform.lower(), source_kind="email",
        ))
        if len(jobs) >= MAX_LEADS_PER_RUN:
            break
    return jobs


def fetch_email_alerts(*, imap_factory=None) -> list[SearchResult]:
    """Read only a dedicated IMAP folder. Secrets must come from environment.

    Uses TLS and readonly IMAP FETCH BODY.PEEK[] so no mail is marked read.
    """
    host = os.getenv("JOB_ALERT_IMAP_HOST", "").strip()
    user = os.getenv("JOB_ALERT_IMAP_USER", "").strip()
    password = os.getenv("JOB_ALERT_IMAP_PASSWORD", "")
    folder = os.getenv("JOB_ALERT_IMAP_FOLDER", "JobRadar").strip()
    if not host or not user or not password:
        raise ValueError("Missing JOB_ALERT_IMAP_HOST / USER / PASSWORD")
    if not re.fullmatch(r"[A-Za-z0-9.-]{3,200}", host):
        raise ValueError("Invalid IMAP hostname")
    # A folder is user-configured, not a command. Restrict quotes/escapes.
    if not folder or len(folder) > 80 or any(ch in folder for ch in '\\"\r\n'):
        raise ValueError("Invalid IMAP folder")
    factory = imap_factory or imaplib.IMAP4_SSL
    with factory(host, 993, ssl_context=ssl.create_default_context(), timeout=20) as imap:
        imap.login(user, password)
        status, _ = imap.select(folder, readonly=True)
        if status != "OK":
            raise RuntimeError("Unable to open job-alert folder")
        days = max(1, min(14, int(os.getenv("JOB_ALERT_LOOKBACK_DAYS", "7"))))
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
        status, found = imap.uid("SEARCH", None, "SINCE", since)
        if status != "OK":
            raise RuntimeError("IMAP SEARCH failed")
        uids = (found[0] if found else b"").split()[-min(60, max(1, int(os.getenv("JOB_ALERT_MAX_EMAILS", "40")))):]
        jobs: list[SearchResult] = []
        for uid in uids:
            status, items = imap.uid("FETCH", uid, "(BODY.PEEK[])")
            if status != "OK":
                continue
            raw = next((part[1] for part in (items or []) if isinstance(part, tuple) and isinstance(part[1], bytes)), b"")
            jobs.extend(parse_alert_message(raw, max_age_days=days))
            if len(jobs) >= MAX_LEADS_PER_RUN:
                break
        return jobs[:MAX_LEADS_PER_RUN]
