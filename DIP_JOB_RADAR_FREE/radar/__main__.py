
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from dotenv import load_dotenv
from search.rss_search import GoogleNewsRSS, build_queries
from radar.database import JobDB, fingerprint
from radar.scoring import score_job
from radar.telegram import format_job, send_message


ROOT = Path(__file__).resolve().parents[1]
MAX_JOB_AGE_DAYS = 14


def is_recent(job, now=None):
    """Accept jobs with a valid publication date within the last 14 days."""
    now = now or datetime.now(timezone.utc)

    if not job.published:
        return False

    try:
        published_at = parsedate_to_datetime(job.published)

        if published_at is None:
            return False

        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)

        published_at = published_at.astimezone(timezone.utc)
        age = now - published_at

        return timedelta(0) <= age <= timedelta(
            days=MAX_JOB_AGE_DAYS
        )

    except (TypeError, ValueError, OverflowError):
        return False


def main():
    load_dotenv(ROOT / ".env")

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    dry = os.getenv("DRY_RUN", "1").strip() == "1"
    threshold = int(os.getenv("MIN_SCORE", "60"))
    limit = int(os.getenv("MAX_RESULTS_PER_QUERY", "15"))

    if not dry and (not token or not chat_id):
        raise SystemExit(
            "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"
        )

    keywords = json.loads(
        (ROOT / "config/keywords.json").read_text(encoding="utf-8")
    )

    db = JobDB(ROOT / "data/jobs.sqlite3")
    searcher = GoogleNewsRSS()
    all_jobs = {}
    queries = build_queries()

    for query in queries:
        try:
            for job in searcher.search(query, limit):
                fp = fingerprint(job.url, job.title)
                all_jobs.setdefault(fp, job)
        except Exception as error:
            print(f"[WARN] Feed failed: {query} :: {error}")

    matches = []
    skipped_old = 0
    skipped_location = 0
    skipped_seen = 0

    for fp, job in all_jobs.items():
        if not is_recent(job):
            skipped_old += 1
            continue

        if not dry and db.seen(fp):
            skipped_seen += 1
            continue

        location_text = (
            f"{job.title} {job.description} {job.url}"
        ).lower()

        if "ahmedabad" not in location_text:
            skipped_location += 1
            continue

        scored = score_job(job, keywords)

        if scored.score >= threshold:
            matches.append((fp, job, scored))

    matches.sort(key=lambda item: item[2].score, reverse=True)

    print(
        f"Queries: {len(queries)} | "
        f"Unique results: {len(all_jobs)} | "
        f"Skipped old/unknown dates: {skipped_old} | "
        f"Skipped location: {skipped_location} | "
        f"Skipped duplicates: {skipped_seen} | "
        f"Matches: {len(matches)}"
    )

    for fp, job, scored in matches[:20]:
        if dry:
            print(
                f"\n--- DRY RUN {scored.score}/100 ---\n"
                f"{job.title}\n"
                f"Published: {job.published}\n"
                f"{job.url}\n"
                + "\n".join(scored.reasons)
            )
        else:
            try:
                send_message(token, chat_id, format_job(job, scored))
                db.add(fp, job, scored.score, True)
                print(
                    f"[SENT] {scored.score} | "
                    f"{job.published} | {job.title}"
                )
            except Exception as error:
                print(
                    f"[ERROR] Telegram send failed: {error}"
                )

    db.close()


if __name__ == "__main__":
    main()
