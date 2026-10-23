"""Extract *separate* designer-role leads from submitted/public hiring text.

Never fetches LinkedIn or assumes an extracted role is a verified vacancy.
The input must be a user-supplied post or text from a permitted discovery feed.
"""
from __future__ import annotations

import re
from radar.verification import role_groups
from search.rss_search import SearchResult

ROLE_MENTIONS = re.compile(
    r"(?<![\w])(?:(?:junior|jr\.?|associate|senior|sr\.?|lead|principal|intern(?:ship)?|trainee)\s+)?"
    r"(?:UI\s*[/&+\-]\s*UX|UX\s*[/&+\-]\s*UI|UI\s+UX|UX\s+UI|"
    r"user\s+experience|user\s+interface|UI|UX|product|interaction|"
    r"graphic|graphics|visual|brand|creative|digital|web)\s+"
    r"design(?:er|ers)?\b", re.I,
)
HIRING = re.compile(
    r"\b(?:we(?:'|’)?re\s+hiring|hiring|open\s+positions?|job\s+openings?|"
    r"vacanc(?:y|ies)|looking\s+for|join\s+our\s+team|apply\s+(?:here|now)|"
    r"send\s+(?:your\s+)?(?:cv|resume))\b", re.I,
)
CITY = re.compile(r"\b(Ahmedabad|Gandhinagar)\b", re.I)
REMOTE_INDIA = re.compile(r"\bremote\b.{0,36}\bIndia\b|\bIndia\b.{0,36}\bremote\b", re.I | re.S)


def extract_role_titles(text: str, allowed: set[str] | None = None) -> list[str]:
    """Extract distinct role titles, preserving seniority for correct rejection.

    Important: 'Graphic Designer & UI/UX Designer' yields UI/UX only when
    allowed excludes graphic; 'Senior and Junior Product Designer' is not
    expanded because the junior title was not explicitly stated.
    """
    results, seen = [], set()
    for match in ROLE_MENTIONS.finditer(text or ""):
        title = " ".join(match.group(0).split()).strip()
        groups = role_groups(title)
        if allowed is not None and not (groups & allowed):
            continue
        key = title.casefold()
        if key not in seen:
            results.append(title)
            seen.add(key)
    return results


def extract_hiring_leads(
    text: str, *, url: str, source: str, company: str = "",
    published: str = "", allowed: set[str] | None = None,
    source_kind: str = "post", location: str = "",
) -> list[SearchResult]:
    """Return unverified roles only when vacancy intent occurs in post text.

    Do not infer a city from a search query. Exact supplied location is
    authoritative; otherwise only extract cities literally in the post.
    """
    if not text or not HIRING.search(text):
        return []
    roles = extract_role_titles(text, allowed)
    if not roles:
        return []
    match_city = CITY.search(text)
    evidence_location = location or (match_city.group(1) if match_city else ("Remote - India" if REMOTE_INDIA.search(text) else ""))
    compact = " ".join(text.split())[:2500]
    # Different vacancies inside one announcement can have different minimum
    # experience requirements. Never apply a senior role's 5+ years to a junior
    # role in the same post. Each role retains only its nearest role segment.
    mentions = [m for m in ROLE_MENTIONS.finditer(text)
                if allowed is None or role_groups(m.group(0)) & allowed]
    def role_description(title):
        if len(roles) == 1:
            return compact
        matching = next((i for i, m in enumerate(mentions)
                         if " ".join(m.group(0).split()).casefold() == title.casefold()), None)
        if matching is None:
            return compact
        current = mentions[matching]
        end = mentions[matching + 1].start() if matching + 1 < len(mentions) else len(text)
        # Do not import unrelated experience requirements appearing before the
        # title. Include explicit location as a separately extracted field.
        excerpt = " ".join(text[current.end():end].split())[:500]
        return "Hiring announcement for " + title + ". " + excerpt
    return [SearchResult(
        title=title, url=url, description=role_description(title),
        published=published, company=company, source=source,
        location=evidence_location, source_kind=source_kind,
        # Never call a post link an application URL.
        apply_url="",
    ) for title in roles]


def expand_rss_hiring_announcements(jobs: list[SearchResult], allowed: set[str]) -> list[SearchResult]:
    """Keep normal RSS jobs, split only clear multi-role hiring announcements.

    All output remains UNVERIFIED, even if its headline resembles a job posting.
    """
    out = []
    for job in jobs:
        if job.source_kind != "rss":
            out.append(job)
            continue
        text = f"{job.title}\n{job.description}"
        roles = extract_role_titles(text, allowed)
        if len(roles) > 1 and HIRING.search(text):
            split = extract_hiring_leads(
                text, url=job.url, source=job.source,
                company=job.company, published=job.published,
                allowed=allowed, location=job.location,
            )
            out.extend(split if split else [job])
        elif not role_groups(job.title) and roles and HIRING.search(text):
            out.extend(extract_hiring_leads(
                text, url=job.url, source=job.source,
                company=job.company, published=job.published,
                allowed=allowed, location=job.location,
            ))
        else:
            out.append(job)
    return out
