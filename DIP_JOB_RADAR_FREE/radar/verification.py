"""Conservative, explainable verification of individual designer vacancies.

Location rules use employer-posted evidence, not a search query or employer name.
An India-only location is NOT automatically treated as remote.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from radar.scoring import contains

NON_JOBS = (
    "training", "course", "certification", "workshop", "webinar", "tutorial",
    "tips for", "how to become", "salary guide", "job market", "career advice",
    "best companies", "interview questions", "resume tips", "free classes",
)
SENIOR_TITLES = (
    "senior", "sr.", "sr ", "lead", "principal", "head of", "director", "manager",
    "intern", "internship", "trainee", "apprentice",
)
WRONG_TITLES = (
    "graphic designer", "graphics designer", "graphic design", "graphics design",
    "brand designer", "social media designer", "packaging designer", "marketing designer",
    "visual designer", "creative designer",
    "video editor", "motion graphic", "interior designer", "fashion designer",
    "architect", "3d artist", "ux researcher", "design engineer", "design architect",
)
SEARCH_PAGES = ("/jobs/search", "/jobs?q=", "/search/jobs", "/job-search", "/jobs-in-", "/jobs/?", "/search?")
HIRING_TOKENS = (
    "hiring", "vacancy", "job opening", "opening for", "apply", "recruit",
    "position", "career opportunity", "looking for", "join our team",
)

# Groups match candidate preferences, not indiscriminately every designer variant.
# The special UIUX group also recognizes UI UX, UX/UI, and user experience/interface.
ROLE_PATTERNS = {
    # Require an actual design occupation; "UI/UX Developer" is not a designer role.
    "uiux": re.compile(r"(?<!\w)(?:ui\s*[/&+\-]\s*ux|ux\s*[/&+\-]\s*ui|ui\s+ux|ux\s+ui)(?:\s+|[-:]\s*)(?:design(?:er|ers)?|design\s+specialist|specialist)\b", re.I),
    "ui": re.compile(r"(?<!\w)(?:ui|user[ -]interface)\s+(?:design(?:er|ers)?|specialist)\b", re.I),
    "ux": re.compile(r"(?<!\w)(?:ux|user[ -]experience)\s+(?:design(?:er|ers)?|specialist)\b", re.I),
    "product": re.compile(r"(?<!\w)(?:digital\s+)?product\s+(?:designers?|design\s+specialist)\b", re.I),
    "visual": re.compile(r"(?<!\w)visual\s+design(?:er|ers|\s+specialist)?\b", re.I),
    "interaction": re.compile(r"(?<!\w)interaction\s+design(?:er|ers)?\b", re.I),
    "graphic": re.compile(r"(?<!\w)graphics?\s+design(?:er|ers|\s+specialist)?\b", re.I),
    "brand": re.compile(r"(?<!\w)brand\s+design(?:er|ers)?\b", re.I),
    "creative": re.compile(r"(?<!\w)creative\s+design(?:er|ers)?\b", re.I),
    "digital": re.compile(r"(?<!\w)digital\s+design(?:er|ers)?\b", re.I),
    "web": re.compile(r"(?<!\w)web\s+design(?:er|ers)?\b", re.I),
}

YEARS_WITH_CONTEXT = re.compile(
    r"(?<!\w)(\d{1,2})\s*(?:\+|to|\-|–)?\s*(?:\d{1,2})?\s*"
    r"(?:years|yrs)\s*(?:of\s+)?(?:relevant\s+|professional\s+|work\s+)?(?:experience|exp)\b", re.I
)
YEARS_WITH_REQUIREMENT = re.compile(
    r"\b(?:requires?|minimum(?: of)?|at least|need(?:s|ed)?|min\.)\s*"
    r"(\d{1,2})\s*(?:\+|to|\-|–)?\s*(?:\d{1,2})?\s*(?:years|yrs)\b", re.I
)
YEARS_LABELLED = re.compile(r"\bexperience\s*:\s*(\d{1,2})\s*(?:\+|to|\-|–)?\s*(?:\d{1,2})?\s*(?:years|yrs)\b", re.I)

# Both India eligibility and remote work must be explicit, or the employer's
# listing must itself say the role is based in one of the preferred cities.
REMOTE_TOKEN = re.compile(r"\bremote(?:ly)?\b|\bwork\s+from\s+home\b|\bwfh\b", re.I)
INDIA_TOKEN = re.compile(r"\bindia\b|\bindian\b", re.I)
REMOTE_NEGATION = re.compile(
    r"\b(?:not|non|no)\s*[- ]?remote\b"
    r"|\bremote\s+(?:(?:work|role|position|option)\s+)?"
    r"(?:not\s+(?:allowed|available)|is\s+not\s+(?:available|allowed|permitted))\b", re.I
)

REMOTE_INDIA_PAIR = re.compile(
    r"\b(?:remote|remotely|work\s+from\s+home|wfh)\b[^.\n;]{0,55}\b(?:india|indian)\b"
    r"|\b(?:india|indian)\b[^.\n;]{0,55}\b(?:remote|remotely|work\s+from\s+home|wfh)\b", re.I
)
# Single generic 'remote' and incidental mention of India are insufficient.
INDIA_ELIGIBILITY = re.compile(
    r"\b(?:based\s+in|located\s+in|resid(?:e|ing|ents?)\s+in|within|anywhere\s+in|from|in)\s+india\b"
    r"|\bindia[- ]based\b|\bindian\s+(?:applicants|candidates|residents)\b", re.I
)


@dataclass(frozen=True)
class Verification:
    accepted: bool
    reason: str
    confidence: str
    required_years: int | None = None


def role_groups(title):
    """Return recognized professional designer categories from the vacancy title."""
    value = title or ""
    found = {group for group, regex in ROLE_PATTERNS.items() if regex.search(value)}
    # 'UI/UX Designer' maps to all three interchangeable user preferences.
    if "uiux" in found:
        found.update({"ui", "ux"})
    return found


def preferred_role_groups(preferred):
    """Derive equivalent groups from explicit user preferences only."""
    selected = set()
    for name in preferred:
        # Treat generic 'ui/ux designer' as equivalent to UI and UX specialties.
        selected.update(role_groups(name))
    return selected


def required_years(text):
    """Extract explicit MINIMUM experience, not company age or maximum of a range."""
    value = text or ""
    hits = [int(hit.group(1)) for pattern in (
        YEARS_WITH_REQUIREMENT, YEARS_LABELLED, YEARS_WITH_CONTEXT
    ) for hit in pattern.finditer(value)]
    return max(hits) if hits else None


def verify_job(job, profile):
    title = (job.title or "").strip()
    desc = job.description or ""
    url = (job.url or "").lower()
    if not role_groups(title):
        return Verification(False, "Not a designer role", "rejected")
    if any(contains(title.lower(), term) for term in WRONG_TITLES):
        return Verification(False, "Excluded occupation", "rejected")
    if any(contains(title.lower(), term) for term in NON_JOBS):
        return Verification(False, "Training, article or advertisement", "rejected")
    if any(x in url for x in SEARCH_PAGES):
        return Verification(False, "Search-results page, not a vacancy", "rejected")
    if profile.get("exclude_senior_roles", True) and any(contains(title.lower(), term) for term in SENIOR_TITLES):
        return Verification(False, "Excluded seniority in vacancy title", "rejected")
    if (job.company or "").casefold() in {c.casefold() for c in profile.get("excluded_companies", [])}:
        return Verification(False, "Company excluded by profile", "rejected")
    years = required_years(desc)
    if years is not None and years > profile.get("max_required_years", 3):
        return Verification(False, f"Requires {years}+ years", "rejected", years)
    try:
        p = urlsplit(job.url)
        if p.scheme != "https" or not p.netloc or p.username:
            return Verification(False, "Unsafe/missing vacancy URL", "rejected", years)
    except (ValueError, TypeError):
        return Verification(False, "Malformed URL", "rejected", years)
    if job.source_kind == "ats" and job.apply_url:
        return Verification(True, "Published individual ATS vacancy", "ats", years)
    if job.source_kind == "email":
        # An alert email is never independent verification, even if RSS leads are opted in.
        return Verification(False, "Job-alert email lead not independently verified", "unverified", years)
    if not any(contains(f"{title} {desc}".lower(), term) for term in HIRING_TOKENS):
        return Verification(False, "No explicit hiring evidence in RSS", "rejected", years)
    if not profile.get("allow_unverified_rss", False):
        return Verification(False, "RSS lead not independently verified", "unverified", years)
    return Verification(True, "RSS hiring lead: manual vacancy check required", "unverified", years)


def evaluate_location(job, profile):
    """Only explicit listing location or India-eligible remote work is accepted."""
    stated = str(getattr(job, "location", "") or "").strip().lower()
    description = str(getattr(job, "description", "") or "").lower()
    title = str(getattr(job, "title", "") or "").lower()
    mode = str(getattr(job, "work_mode", "") or "").strip().lower()
    cities = [str(c).lower().strip() for c in profile.get("locations", ["ahmedabad"]) if c]

    if not profile.get("allow_hybrid", True) and ("hybrid" in stated or mode == "hybrid"):
        return False, "Hybrid role excluded by profile"
    if any(contains(stated, city) for city in cities):
        return True, "Preferred city confirmed in employer location"
    # RSS summaries sometimes include city in the vacancy headline or summary,
    # but the search query itself is intentionally excluded from consideration.
    if job.source_kind == "rss" and any(contains(title + " " + description, city) for city in cities):
        return True, "City stated in RSS content (not independently verified)"
    if not profile.get("allow_remote_india", False):
        return False, "No supported city / India-remote location evidence"
    if REMOTE_NEGATION.search(stated) or REMOTE_NEGATION.search(description):
        return False, "Remote work explicitly excluded"

    # A location of 'Mumbai' or 'United States' must not be overridden just
    # because some generic corporate boilerplate mentions India or remote.
    location_is_india = bool(INDIA_TOKEN.search(stated))
    location_says_remote = bool(REMOTE_TOKEN.search(stated))
    mode_says_remote = mode in ("remote", "fully remote", "work from home", "wfh")
    description_says_remote = bool(REMOTE_TOKEN.search(description))

    if location_is_india and (location_says_remote or mode_says_remote):
        return True, "Remote India confirmed in employer location/work mode"
    if location_is_india and description_says_remote:
        # Require explicit work-mode language in description, not just a mention
        # of 'remote teams' or 'remote collaboration' elsewhere.
        # Some employer vacancies explicitly say "This role is remote" rather
        # than "remote role". Require a role/position statement to prevent
        # incidental wording such as "we collaborate with remote teams".
        if re.search(
            r"\b(?:fully\s+remote|remote\s+(?:position|role|job|work)"
            r"|(?:this|the)\s+(?:role|position|job)\s+is\s+(?:fully\s+)?remote"
            r"|work\s+(?:remotely|from\s+home)|wfh)\b",
            description,
        ):
            return True, "India location and remote work confirmed in vacancy"
    # No specific physical city? Accept only if the text links India eligibility
    # to remote work. Do not consider prose if a different physical city is set.
    location_is_generic = not stated or stated in ("remote", "global", "worldwide", "anywhere", "multiple locations")
    if location_is_generic and (location_says_remote or mode_says_remote or description_says_remote):
        if REMOTE_INDIA_PAIR.search(description) or INDIA_ELIGIBILITY.search(description) and (location_says_remote or mode_says_remote):
            return True, "Remote role with explicit India eligibility"
    return False, "No supported city / India-remote location evidence"
