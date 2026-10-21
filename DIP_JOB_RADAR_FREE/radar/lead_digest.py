"""Optional Telegram digest of *unverified* job-alert email links.

Never conflates email tips with verified jobs or the normal [RUN] eligible count.
Deduplicates only after successful Telegram delivery, using existing DB meta.
"""
from __future__ import annotations

from html import escape

from radar.database import job_fp
from radar.telegram import send_message
from radar.verification import evaluate_location, preferred_role_groups, role_groups, verify_job


def reviewable_email_leads(discovered, profile):
    """Keep only matching role, location and seniority without treating leads as verified."""
    preferences = preferred_role_groups(profile.get("preferred_roles", []))
    found = {}
    for job in discovered:
        if job.source_kind != "email":
            continue
        verdict = verify_job(job, profile)
        if verdict.reason != "Job-alert email lead not independently verified":
            continue
        if not (role_groups(job.title) & preferences):
            continue
        location_ok, _ = evaluate_location(job, profile)
        if not location_ok:
            continue
        found[job_fp(job)] = job
    return found


def send_lead_digest(db, token, chat_id, discovered, profile, *, max_leads=5):
    """Opt-in: send only new matching email tips, clearly marked for manual review."""
    max_leads = max(0, min(int(max_leads), 8))
    if not max_leads:
        return 0, 0
    candidates = reviewable_email_leads(discovered, profile)
    new_leads = [(fp, job) for fp, job in candidates.items()
                 if db.get_meta("email_lead_sent:" + fp) != "1"][:max_leads]
    if not new_leads:
        return len(candidates), 0
    lines = [
        "🔎 <b>DIP JOB RADAR — UNVERIFIED EMAIL LEADS</b>",
        "These links came from alert emails, NOT verified employer vacancies.",
        "Confirm location, employer, experience and availability before applying.",
    ]
    for n, (_, job) in enumerate(new_leads, 1):
        lines.append(
            f'\n{n}. <b>{escape(job.title)}</b> · {escape(job.location)}'
            f'\n{escape(job.source)}'
            f'\n<a href="{escape(job.url, quote=True)}">Open listing to verify</a>'
        )
    send_message(token, chat_id, "\n".join(lines))
    for fp, _ in new_leads:
        db.set_meta("email_lead_sent:" + fp, "1")
    return len(candidates), len(new_leads)
