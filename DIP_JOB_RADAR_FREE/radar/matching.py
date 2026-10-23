"""Explainable V2 matching against explicit candidate preferences.

Every job must pass verification and location gates before scoring. A score
never overrides a missing supported location or an excluded senior role.
"""
from __future__ import annotations

from dataclasses import dataclass

from radar.scoring import matches
from radar.verification import (
    evaluate_location, preferred_role_groups, role_groups, verify_job,
)


@dataclass
class Match:
    accepted: bool
    score: int
    reasons: list[str]
    rejection: str = ""
    verification: str = ""
    required_years: int | None = None


def _candidate_groups(profile, keywords):
    # A user-specified preference is authoritative. Do not re-enable a job
    # category via generic keywords if the user removed it from the profile.
    if "preferred_roles" in profile:
        return preferred_role_groups(profile["preferred_roles"])
    return preferred_role_groups(
        keywords.get("primary_roles", []) + keywords.get("bridge_roles", [])
    )


def evaluate(job, profile, keywords):
    verdict = verify_job(job, profile)
    if not verdict.accepted:
        return Match(False, 0, [], verdict.reason, verdict.confidence, verdict.required_years)

    fits, location_reason = evaluate_location(job, profile)
    if not fits:
        return Match(False, 0, [], location_reason, verdict.confidence, verdict.required_years)

    allowed = _candidate_groups(profile, keywords)
    matched = role_groups(job.title) & allowed
    if not matched:
        return Match(False, 0, [], "Role not in candidate preferences", verdict.confidence, verdict.required_years)

    # V2 scoring deliberately does NOT require the word 'Ahmedabad' to appear
    # in a listing. Verified jobs in Gandhinagar / Remote India are equally
    # valid. Legacy V1 scoring still exists in radar.scoring separately.
    description = (job.description or "").lower()
    # Respect an explicitly configured (even empty) skills preference list.
    skill_terms = profile["skills"] if "skills" in profile else keywords.get("skills", [])
    skills = matches(description, skill_terms)
    product = bool(matches(description, keywords.get("product_signals", [])))

    # Role 35 + valid location 25 + verified employer vacancy 15 gives 75 points.
    # RSS with manual opt-in is explicitly less confident: 35 + 25 + 5 = 65.
    score = 35 + 25 + (15 if job.source_kind in ("ats", "career") else 5)
    score += min(15, 3 * len(skills))
    if product:
        score += 5
    if verdict.required_years is not None and verdict.required_years <= profile.get("max_required_years", 3):
        score += 3
    score = min(score, 100)

    reasons = [verdict.reason, location_reason, "Preferred designer role: " + ", ".join(sorted(matched))]
    if skills:
        reasons.append("Skills: " + ", ".join(skills[:5]))
    if verdict.required_years is not None:
        reasons.append(f"Minimum experience: {verdict.required_years} years")
    if job.source_kind in ("ats", "career"):
        reasons.append("Role listed on public employer vacancy page")
    else:
        reasons.append("RSS: confirm opening on the employer website before applying")
    return Match(True, score, reasons, "", verdict.confidence, verdict.required_years)
