"""DIP JOB RADAR: collect, filter, score and send job alerts to Telegram."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from radar.database import JobDB, fingerprint
from radar.dates import date_status
from radar.notify import maybe_send_feed_alert, maybe_send_heartbeat
from radar.scoring import LOCATION_NONE, LOCATION_WEAK, location_level, score_job
from radar.telegram import format_job, send_message
from search.rss_search import GoogleNewsRSS, build_queries

ROOT = Path(__file__).resolve().parents[1]

MAX_ALERTS_PER_RUN = 20
FEED_FAILURE_ALERT_RATIO = 0.5  # alert when more than half of the feeds fail


def env_int(name, default):
    return int(os.getenv(name) or default)


def env_float(name, default):
    return float(os.getenv(name) or default)


@dataclass
class Classified:
    matches: list = field(default_factory=list)  # (fingerprint, job, scored)
    below: list = field(default_factory=list)  # (score, job)
    date_counts: dict = field(
        default_factory=lambda: {"missing": 0, "invalid": 0, "future": 0, "old": 0}
    )
    skipped_location: int = 0
    skipped_seen: int = 0
    weak_location: int = 0


def collect_jobs(searcher, queries, limit, delay=0.0):
    """Run every query. Returns ({fingerprint: job}, number_of_failed_queries)."""
    jobs = {}
    failures = 0

    for index, query in enumerate(queries):
        if index and delay:
            time.sleep(delay)
        try:
            for job in searcher.search(query, limit):
                jobs.setdefault(fingerprint(job.url, job.title), job)
        except Exception as error:
            failures += 1
            print(f"[WARN] Feed failed: {query} :: {error}")

    return jobs, failures


def classify(all_jobs, db, keywords, threshold, dry, max_age_days=14, now=None):
    """Apply date, duplicate, location and score filters to the collected jobs."""
    result = Classified()

    for fp, job in all_jobs.items():
        status = date_status(job, now=now, max_age_days=max_age_days)

        if status != "ok":
            result.date_counts[status] += 1
            continue

        if not dry and db.seen(fp):
            result.skipped_seen += 1
            continue

        level = location_level(job, keywords)

        if level == LOCATION_NONE:
            result.skipped_location += 1
            continue

        if level == LOCATION_WEAK:
            result.weak_location += 1

        scored = score_job(job, keywords)

        if scored.score >= threshold:
            result.matches.append((fp, job, scored))
        else:
            result.below.append((scored.score, job))

    result.matches.sort(key=lambda item: item[2].score, reverse=True)
    result.below.sort(key=lambda item: item[0], reverse=True)
    return result


def print_summary(queries, failures, all_jobs, result, threshold):
    counts = result.date_counts
    skipped_dates = sum(counts.values())

    print(
        f"Queries: {len(queries)} | "
        f"Feed failures: {failures} | "
        f"Unique results: {len(all_jobs)} | "
        f"Skipped old/unknown dates: {skipped_dates} "
        f"(old={counts['old']}, missing={counts['missing']}, "
        f"invalid={counts['invalid']}, future={counts['future']}) | "
        f"Skipped location: {result.skipped_location} | "
        f"Skipped duplicates: {result.skipped_seen} | "
        f"City only via query: {result.weak_location} | "
        f"Below score {threshold}: {len(result.below)} | "
        f"Matches: {len(result.matches)}"
    )

    # Why fresh Ahmedabad jobs were NOT sent (top 15 by score)
    for score, job in result.below[:15]:
        print(f"[LOW SCORE] {score}/{threshold} | {job.published} | {job.title}")


def deliver(result, db, token, chat_id, dry):
    for fp, job, scored in result.matches[:MAX_ALERTS_PER_RUN]:
        if dry:
            print(
                f"\n--- DRY RUN {scored.score}/100 ---\n"
                f"{job.title}\n"
                f"Published: {job.published}\n"
                f"{job.url}\n" + "\n".join(scored.reasons)
            )
            continue

        try:
            send_message(token, chat_id, format_job(job, scored))
            db.add(fp, job, scored.score, True)
            print(f"[SENT] {scored.score} | {job.published} | {job.title}")
        except Exception as error:
            print(f"[ERROR] Telegram send failed: {error}")


def main():
    load_dotenv(ROOT / ".env")

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    dry = os.getenv("DRY_RUN", "1").strip() == "1"
    threshold = env_int("MIN_SCORE", 60)
    limit = env_int("MAX_RESULTS_PER_QUERY", 15)
    max_age_days = env_int("MAX_JOB_AGE_DAYS", 14)
    delay = env_float("QUERY_DELAY_SECONDS", 0.5)

    can_notify = not dry and bool(token) and bool(chat_id)

    if not dry and not can_notify:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    keywords = json.loads((ROOT / "config/keywords.json").read_text(encoding="utf-8"))

    db = JobDB(ROOT / "data/jobs.sqlite3")
    queries = build_queries()

    all_jobs, failures = collect_jobs(GoogleNewsRSS(), queries, limit, delay)

    if failures:
        print(f"::warning::{failures} of {len(queries)} search feeds failed")

        if failures / len(queries) > FEED_FAILURE_ALERT_RATIO and can_notify:
            maybe_send_feed_alert(db, token, chat_id, failures, len(queries))

    if failures == len(queries):
        db.close()
        raise SystemExit("All search feeds failed - nothing to process")

    result = classify(all_jobs, db, keywords, threshold, dry, max_age_days)
    print_summary(queries, failures, all_jobs, result, threshold)
    deliver(result, db, token, chat_id, dry)

    if can_notify:
        fresh = len(all_jobs) - sum(result.date_counts.values())
        summary = (
            f"{len(all_jobs)} results, {fresh} fresh, "
            f"{len(result.matches)} matches, {failures} feed failures"
        )
        maybe_send_heartbeat(db, token, chat_id, summary)

    db.close()


if __name__ == "__main__":
    main()
