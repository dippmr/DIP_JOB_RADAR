"""Explainable job matching after mandatory verification gates."""
from __future__ import annotations
from dataclasses import dataclass
from radar.scoring import contains, score_job
from radar.verification import evaluate_location, verify_job


@dataclass
class Match:
    accepted: bool
    score: int
    reasons: list[str]
    rejection: str = ""
    verification: str = ""
    required_years: int | None = None


def evaluate(job, profile, keywords):
    verdict = verify_job(job, profile)
    if not verdict.accepted:
        return Match(False, 0, [], verdict.reason, verdict.confidence, verdict.required_years)
    fits, loc_reason = evaluate_location(job, profile)
    if not fits:
        return Match(False, 0, [], loc_reason, verdict.confidence, verdict.required_years)
    title = job.title.lower()
    roles = profile.get("preferred_roles", [])
    relevant = [r for r in roles if contains(title, r)]
    if not relevant:
        # Existing keywords can still recognize uncommon bridge roles.
        if not any(contains(title, r) for r in keywords.get("primary_roles", []) + keywords.get("bridge_roles", [])):
            return Match(False, 0, [], "Role not in candidate preferences", verdict.confidence)
    # Existing score anchors role and skill matching; direct ATS vacancy provides independent evidence.
    base = score_job(job, keywords).score
    if job.source_kind == "ats":
        base = max(base, 46) + 20
    else:
        # Do not treat the Ahmedabad-only RSS query as proof of location.
        base = min(base, 82)
    skill_matches = [skill for skill in profile.get("skills", []) if contains(job.description.lower(), skill)]
    score = min(100, base + min(15, len(skill_matches) * 3) + (6 if relevant else 0))
    reasons = [verdict.reason, loc_reason]
    if relevant:
        reasons.append("Preferred role: " + relevant[0])
    if skill_matches:
        reasons.append("Skills: " + ", ".join(skill_matches[:5]))
    if verdict.required_years is not None:
        reasons.append(f"Experience requested: {verdict.required_years}+ years")
    if job.source_kind == "ats":
        reasons.append("Apply on company/ATS vacancy page")
    return Match(True, score, reasons, "", verdict.confidence, verdict.required_years)
