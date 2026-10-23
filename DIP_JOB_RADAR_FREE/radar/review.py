"""Separate unverified *relevant* hiring leads from immediate verified alerts."""
from __future__ import annotations

from radar.verification import (
    HIRING_TOKENS, evaluate_location, preferred_role_groups,
    required_years, role_groups, verify_job,
)
from radar.scoring import contains

UNVERIFIED_REASONS = frozenset({
    "Job-alert email lead not independently verified",
    "RSS lead not independently verified",
    "Hiring post not independently verified",
    "Employer careers index: individual role not confirmed",
})


def review_reason(job, profile):
    """Return a reason only for an explicitly relevant, location-supported lead.

    This queue has NO automatic job-alert status and NEVER implies verification.
    """
    allowed = preferred_role_groups(profile.get("preferred_roles", []))
    if not (role_groups(job.title) & allowed):
        return ""
    verdict = verify_job(job, profile)
    if verdict.reason not in UNVERIFIED_REASONS:
        return ""
    if not evaluate_location(job, profile)[0]:
        return ""
    content = f"{job.title} {job.description}".lower()
    if not any(contains(content, token) for token in HIRING_TOKENS):
        return ""
    return verdict.reason
