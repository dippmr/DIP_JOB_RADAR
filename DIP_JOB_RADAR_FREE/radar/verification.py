"""Hard rejection and evidence-based job validation."""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from radar.scoring import contains, matches

NON_JOBS = (
    "training", "course", "certification", "workshop", "webinar", "tutorial",
    "tips for", "how to become", "salary guide", "job market", "career advice",
    "best companies", "interview questions", "resume tips", "free classes",
)
SENIOR_TITLES = ("senior", "sr.", "lead", "principal", "head of", "director", "manager", "intern", "internship", "trainee")
WRONG_TITLES = ("video editor", "motion graphic", "interior designer", "fashion designer", "architect", "3d artist", "ux researcher")
SEARCH_PAGES = ("/jobs/search", "/jobs?q=", "/search/jobs", "/job-search", "/jobs-in-", "/jobs/?", "/search?")
ROLE_TOKENS = ("designer", "design", "ux", "ui")
HIRING_TOKENS = ("hiring", "vacancy", "job opening", "opening for", "apply", "recruit", "position", "career opportunity", "looking for", "join our team")
YEARS_WITH_CONTEXT = re.compile(
    r"(?<!\w)(\d{1,2})\s*(?:\+|to|\-|–)?\s*(?:\d{1,2})?\s*(?:years|yrs)\s*(?:of\s+)?(?:experience|exp)\b", re.I
)
YEARS_WITH_REQUIREMENT = re.compile(
    r"\b(?:requires?|minimum(?: of)?|at least|need(?:s|ed)?|min\.)\s*(\d{1,2})\s*(?:\+|to|\-|–)?\s*(?:\d{1,2})?\s*(?:years|yrs)\b", re.I
)


@dataclass(frozen=True)
class Verification:
    accepted: bool
    reason: str
    confidence: str  # verified ATS listing, unverified RSS listing
    required_years: int | None = None


def required_years(text):
    """Extract conservative minimum experience; reject only explicit min greater than preference."""
    for pattern in (YEARS_WITH_CONTEXT, YEARS_WITH_REQUIREMENT):
        hit = pattern.search(text or "")
        if hit:
            return int(hit.group(1))
    return None


def verify_job(job, profile):
    title = (job.title or "").lower().strip()
    desc = (job.description or "").lower()
    url = (job.url or "").lower()
    if not any(contains(title, x) for x in ROLE_TOKENS):
        return Verification(False, "Not a designer role", "rejected")
    if any(contains(title, x) for x in WRONG_TITLES):
        return Verification(False, "Excluded occupation", "rejected")
    if any(contains(title, x) for x in NON_JOBS):
        return Verification(False, "Training, article or advertisement", "rejected")
    if any(x in url for x in SEARCH_PAGES):
        return Verification(False, "Search-results page, not a vacancy", "rejected")
    if profile.get("exclude_senior_roles", True) and any(contains(title, x) for x in SENIOR_TITLES):
        return Verification(False, "Excluded seniority in vacancy title", "rejected")
    if (job.company or "").casefold() in {c.casefold() for c in profile.get("excluded_companies", [])}:
        return Verification(False, "Company excluded by profile", "rejected")
    years = required_years(desc)
    if years is not None and years > profile.get("max_required_years", 3):
        return Verification(False, f"Requires {years}+ years", "rejected", years)
    try:
        p = urlsplit(job.url)
        if p.scheme != "https" or not p.netloc:
            return Verification(False, "Unsafe/missing vacancy URL", "rejected", years)
    except ValueError:
        return Verification(False, "Malformed URL", "rejected", years)
    if job.source_kind == "ats" and job.apply_url:
        return Verification(True, "Published individual ATS vacancy", "ats", years)
    if not any(contains(f"{title} {desc}", x) for x in HIRING_TOKENS):
        return Verification(False, "No explicit hiring evidence in RSS", "rejected", years)
    if not profile.get("allow_unverified_rss", False):
        return Verification(False, "RSS lead not independently verified", "unverified", years)
    return Verification(True, "RSS hiring lead: manual vacancy check required", "unverified", years)


def evaluate_location(job, profile):
    """Strict city evidence. RSS query text never counts as evidence."""
    text = f"{job.location} {job.title} {job.description}".lower()
    cities = [c.lower() for c in profile.get("locations", ["ahmedabad"])]
    stated_location = (job.location or "").lower()
    remote = bool(re.search(r"\bremote\b", stated_location))
    if any(contains(stated_location or text, city) for city in cities):
        if not profile.get("allow_hybrid", True) and "hybrid" in stated_location:
            return False, "Hybrid role excluded by profile"
        return True, "Location verified from listing"
    if not profile.get("allow_hybrid", True) and "hybrid" in stated_location:
        return False, "Hybrid role excluded by profile"
    if job.source_kind == "rss" and any(contains(text, city) for city in cities):
        return True, "City mentioned in RSS content (not independently verified)"
    # India-specific remote. Ambiguous world-wide remote is excluded.
    if remote and profile.get("allow_remote_india", False) and any(x in stated_location for x in ("india", "indian")):
        return True, "Remote: check India eligibility"
    return False, "No supported city / India-remote location evidence"
