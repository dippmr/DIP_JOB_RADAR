"""Targeted Google News RSS *leads*; not direct LinkedIn/Naukri/etc access.

The eight website domains are searched through an independent RSS index.
These results are unverified and never promoted to published ATS vacancies.
"""
from __future__ import annotations

from datetime import datetime, timezone

PLATFORMS = {
    "LinkedIn": "linkedin.com/jobs",
    "Naukri": "naukri.com",
    "Indeed": "in.indeed.com",
    "Apna": "apna.co",
    "Internshala": "internshala.com",
    "Wellfound": "wellfound.com",
    "Cutshort": "cutshort.io",
    "Behance": "behance.net/joblist",
}


def platform_queries() -> list[tuple[str, str]]:
    """One geographically relevant query per board/site and intent."""
    out = []
    for name, domain in PLATFORMS.items():
        for job_query in (
            '"Ahmedabad" ("graphic designer" OR "UI UX designer" OR "product designer") hiring',
            '"Gandhinagar" ("graphic designer" OR "UI UX designer" OR "visual designer") hiring',
            '("remote India" OR "work from home India") ("graphic designer" OR "UI UX designer" OR "product designer")',
        ):
            out.append((name, f"site:{domain} {job_query}"))
    return out


def rotate_platform_queries(*, per_run: int = 4, now: datetime | None = None) -> list[tuple[str, str]]:
    """Rotate 24 queries across six 15-minute slots (UTC)."""
    if per_run < 0:
        raise ValueError("per_run must be non-negative")
    queries = platform_queries()
    now = now or datetime.now(timezone.utc)
    slot = (now.hour * 4 + now.minute // 15)
    start = (slot * max(1, per_run)) % len(queries)
    return [queries[(start + offset) % len(queries)] for offset in range(min(per_run, len(queries)))]
