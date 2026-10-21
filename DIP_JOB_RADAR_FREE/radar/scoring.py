"""Relevance scoring: turns a search result into a 0-100 score with reasons."""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- Points per signal (the maximum possible total is at least 100) ---
LOCATION_IN_TEXT = 10  # city found in title/description/url (not just the query)
PRIMARY_ROLE = 35
BRIDGE_ROLE = 15
SKILL_EACH = 3
SKILL_MAX = 15
PRODUCT_SIGNAL = 5
HIRING_SIGNAL = 20
HASHTAG = 5

# --- Penalties ---
EXCLUDE_EACH = 30
EXCLUDE_MAX = 60
SENIORITY = 25

# Used only if config/keywords.json has no "seniority_terms" list.
DEFAULT_SENIORITY_TERMS = [
    "senior",
    "lead designer",
    "design lead",
    "design manager",
    "head of design",
    "principal",
]

LOCATION_STRONG = "strong"  # city appears in the result itself
LOCATION_WEAK = "weak"  # city appears only in the search query that found it
LOCATION_NONE = "none"


@dataclass
class ScoredJob:
    score: int
    reasons: list[str]
    negative_reasons: list[str]
    location: str = LOCATION_STRONG


def job_text(job):
    parts = (
        getattr(job, "title", ""),
        getattr(job, "description", ""),
        getattr(job, "url", ""),
        getattr(job, "source", ""),
    )
    return " ".join(str(part or "") for part in parts).lower()


def contains(text, term):
    """Whole-word / whole-phrase match. A trailing 's' is allowed (plurals).

    The lookarounds work for terms that start or end with symbols such as
    '#hiring' or 'ui/ux designer', which a plain \\b word boundary cannot match.
    """
    term = term.lower().strip()
    if not term:
        return False
    return re.search(rf"(?<!\w){re.escape(term)}s?(?!\w)", text) is not None


def matches(text, terms):
    return [term for term in terms if contains(text, term)]


def location_level(job, keywords):
    """Return LOCATION_STRONG, LOCATION_WEAK or LOCATION_NONE.

    Google News usually gives only a headline, so the city is often missing
    from the result text even though the search query required it. In that
    case the result is kept as WEAK so the alert can say "please verify".
    """
    terms = keywords["location"]["required"]

    if matches(job_text(job), terms):
        return LOCATION_STRONG

    query = str(getattr(job, "query", "") or "").lower()
    if any(term.lower() in query for term in terms):
        return LOCATION_WEAK

    return LOCATION_NONE


def score_job(job, keywords):
    level = location_level(job, keywords)

    if level == LOCATION_NONE:
        return ScoredJob(0, [], ["No Ahmedabad signal"], level)

    text = job_text(job)
    score = 0
    reasons = []
    negative = []

    if level == LOCATION_STRONG:
        score += LOCATION_IN_TEXT
        reasons.append("Ahmedabad match")
    else:
        reasons.append("Ahmedabad (search query only)")

    primary = matches(text, keywords.get("primary_roles", []))
    if primary:
        score += PRIMARY_ROLE
        reasons.append("Target role: " + primary[0])

    if matches(text, keywords.get("bridge_roles", [])):
        score += BRIDGE_ROLE
        reasons.append("Graphic → UI/UX bridge role")

    skills = matches(text, keywords.get("skills", []))
    if skills:
        score += min(SKILL_MAX, SKILL_EACH * len(skills))
        reasons.append("Skills: " + ", ".join(skills[:4]))

    if matches(text, keywords.get("product_signals", [])):
        score += PRODUCT_SIGNAL
        reasons.append("Product signal")

    if matches(text, keywords.get("hiring_signals", [])):
        score += HIRING_SIGNAL
        reasons.append("Hiring signal")

    if matches(text, keywords.get("hashtags", [])):
        score += HASHTAG
        reasons.append("Hiring hashtag")

    excluded = matches(text, keywords.get("exclude_terms", []))
    if excluded:
        score -= min(EXCLUDE_MAX, EXCLUDE_EACH * len(excluded))
        negative += [f"Excluded: {term}" for term in excluded]
    else:
        # Only checked when nothing was excluded, so "Senior Product Designer"
        # is not penalised twice for the same word.
        seniority = keywords.get("seniority_terms", DEFAULT_SENIORITY_TERMS)
        if matches(text, seniority):
            score -= SENIORITY
            negative.append("Senior/leadership signal")

    return ScoredJob(max(0, min(100, score)), reasons, negative, level)
