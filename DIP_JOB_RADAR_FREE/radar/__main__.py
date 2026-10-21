from __future__ import annotations

import json
import os
import sqlite3
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

# Daily "I am alive" message: sent by the first run at/after this hour (IST)
IST = timezone(timedelta(hours=5, minutes=30))
HEARTBEAT_HOUR_IST = 9


def date_status(job, now=None):
    """Return 'ok', 'missing', 'invalid', 'future' or 'old'."""
    now = now or datetime.now(timezone.utc)

    if not job.published:
        return "missing"

    try:
        published_at = parsedate_to_datetime(job.published)

        if published_at is None:
            return "invalid"

        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)

        age = now - published_at.astimezone(timezone.utc)

        if age < timedelta(0):
            return "future"

        if age > timedelta(days=MAX_JOB_AGE_DAYS):
            return "old"

        return "ok"

    except (TypeError, ValueError, OverflowError):
        return "invalid"


def is_recent(job, now=None):
    return date_status(job, now) == "ok"


def maybe_send_heartbeat(db_path, token, chat_id, summary):
    """Send one Telegram status message per day (IST). Never crashes the run."""
    try:
        now_ist = datetime.now(IST)

        if now_ist.hour < HEARTBEAT_HOUR_IST:
            return

        today = now_ist.strftime("%Y-%m-%d")
        con = sqlite3.connect(db_path)

        try:
            con.execute(
                "CREATE TABLE IF NOT EXISTS meta "
                "(key TEXT PRIMARY KEY, value TEXT)"
            )
            row = con.execute(
                "SELECT value FROM meta WHERE key = 'last_heartbeat'"
            ).fetchone()

            if row and row[0] == today:
                return

            send_message(
                token,
                chat_id,
                "DIP JOB RADAR is alive ("
                + today
                + ")\nLast run: "
                + summary,
            )
            con.execute(
                "INSERT OR REPLACE INTO meta (key, value) "
                "VALUES ('last_heartbeat', ?)",
                (today,),
            )
            con.commit()
            print("[HEARTBEAT] sent")
        finally:
            con.close()

    except Exception as error:
        print(f"[WARN] Heartbeat failed: {error}")


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

    db_path = ROOT / "data/jobs.sqlite3"
    db = JobDB(db_path)
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
    below_threshold = []
    date_counts = {"missing": 0, "invalid": 0, "future": 0, "old": 0}
    skipped_location = 0
    skipped_seen = 0

    for fp, job in all_jobs.items():
        status = date_status(job)

        if status != "ok":
            date_counts[status] += 1
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
        else:
            below_threshold.append((scored.score, job))

    matches.sort(key=lambda item: item[2].score, reverse=True)
    below_threshold.sort(key=lambda item: item[0], reverse=True)

    skipped_old = sum(date_counts.values())

    print(
        f"Queries: {len(queries)} | "
        f"Unique results: {len(all_jobs)} | "
        f"Skipped old/unknown dates: {skipped_old} "
        f"(old={date_counts['old']}, missing={date_counts['missing']}, "
        f"invalid={date_counts['invalid']}, future={date_counts['future']}) | "
        f"Skipped location: {skipped_location} | "
        f"Skipped duplicates: {skipped_seen} | "
        f"Below score {threshold}: {len(below_threshold)} | "
        f"Matches: {len(matches)}"
    )

    # Show why fresh Ahmedabad jobs were NOT sent (top 15 by score)
    for score, job in below_threshold[:15]:
        print(
            f"[LOW SCORE] {score}/{threshold} | "
            f"{job.published} | {job.title}"
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

    if not dry and token and chat_id:
        maybe_send_heartbeat(
            db_path,
            token,
            chat_id,
            f"{len(all_jobs)} results, "
            f"{len(all_jobs) - skipped_old} fresh, "
            f"{len(matches)} matches",
        )


if __name__ == "__main__":
    main()
