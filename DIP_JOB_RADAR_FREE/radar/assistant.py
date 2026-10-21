"""Personal application-preparation checklist/draft. Nothing is ever submitted."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from radar.database import RadarDB as JobDB
from radar.scoring import contains

ROOT = Path(__file__).resolve().parents[1]


def build_application_prep(job, profile):
    skills = [s for s in profile.get("skills", []) if contains((job.get("description") or "").lower(), s)]
    lines = [
        "DIP JOB RADAR — APPLICATION PREPARATION (EDIT BEFORE USE)",
        f"Role: {job['title']}",
        f"Company: {job.get('company') or 'Verify company name'}",
        f"Application URL: {job.get('apply_url') or job['url']}",
        "", "PORTFOLIO CHECKLIST",
        "[ ] Confirm the job is active and genuinely based in your target location",
        "[ ] Check actual responsibilities, salary, work mode and years required",
        "[ ] Choose 1–2 relevant design case studies with measurable outcomes",
        "[ ] Review portfolio and resume before submission",
        "[ ] Check resume claims against your real experience",
        "", "RELEVANT SKILLS MENTIONED IN THIS LISTING",
        ", ".join(skills) if skills else "No profile skills clearly identifiable — review description yourself",
        "", "STARTER INTRODUCTION (PERSONALIZE; DO NOT SEND AS-IS)",
        f"Hello {job.get('company') or 'Hiring Team'} team,",
        f"I'm interested in the {job['title']} opening. My background in [your actual strengths] "
        "and my portfolio project [real project + measurable result] are relevant to [specific responsibility from this listing]. "
        "I'd welcome the chance to discuss how I can contribute. Thank you.",
        "", "FOLLOW-UP TEMPLATE", "Hello, I wanted to follow up on my application for "
        f"the {job['title']} role. Please let me know if I can share any other details. Thank you.",
        "", "Reminder: Do not invent experiences, outcomes, salary, or recruiter names.",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Prepare a manual job application (does not submit anything)")
    parser.add_argument("fingerprint", help="A fingerprint from the dashboard/database; unique prefix is accepted")
    parser.add_argument("--output", help="File path; defaults to printing to screen")
    args = parser.parse_args()
    profile = json.loads((ROOT / "config/profile.json").read_text())
    db = JobDB(ROOT / "data/jobs.sqlite3")
    try:
        rows = [j for j in db.list_opportunities(10000) if j['fingerprint'].startswith(args.fingerprint)]
        if len(rows) != 1:
            raise SystemExit(f"Expected one job; found {len(rows)}. Supply a longer fingerprint.")
        result = build_application_prep(rows[0], profile)
        if args.output:
            Path(args.output).write_text(result, encoding="utf-8")
        else:
            print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
