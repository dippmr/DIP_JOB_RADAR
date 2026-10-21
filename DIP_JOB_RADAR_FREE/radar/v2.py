
"""V2 end-to-end scanner. Start with: python -m radar.v2"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from radar.database import RadarDB as JobDB, job_fp
from radar.dates import date_status
from radar.matching import evaluate
from radar.notify import IST, maybe_send_feed_alert, maybe_send_heartbeat, send_once_per_day
from radar.private_state import PrivateState
from radar.telegram_v2 import receive_feedback, send_alert
from search.ats import fetch_board
from search.rss_search import GoogleNewsRSS, build_queries

ROOT = Path(__file__).resolve().parents[1]


def configuration():
    profile = json.loads((ROOT / "config/profile.json").read_text(encoding="utf-8"))
    keywords = json.loads((ROOT / "config/keywords.json").read_text(encoding="utf-8"))
    boards = json.loads((ROOT / "config/company_watchlist.json").read_text(encoding="utf-8"))["boards"]
    return profile, keywords, boards


def collect(db, boards, *, rss_enabled=True, rss_limit=12, rss_per_query=12, dry=False):
    """Fetch from allowed ATS and rotate through RSS to spread source load."""
    discovered = []
    total, failed = 0, 0
    successful_boards = []
    if boards:
        for board in boards:
            if not board.get("enabled", True):
                continue
            total += 1
            name = f"{board.get('provider')}:{board.get('company')}"
            try:
                jobs = fetch_board(board)
                discovered.extend(jobs)
                successful_boards.append((jobs[0].source if jobs else f"{board['provider'].title()} · {board['company']}", [job_fp(j) for j in jobs]))
                if not dry:
                    db.record_source(name, True)
                print(f"[SOURCE] {name}: {len(jobs)} published listings")
            except Exception as error:
                failed += 1
                if not dry:
                    db.record_source(name, False, type(error).__name__)
                print(f"[WARN] {name}: {type(error).__name__}")
    if rss_enabled:
        queries = build_queries()
        # Deterministic rotation: complete a 48-query circuit in four 15-minute runs.
        slot = (datetime.now(timezone.utc).hour * 4 + datetime.now(timezone.utc).minute // 15)
        start = (slot * max(1, rss_limit)) % len(queries)
        chosen = [queries[(start + x) % len(queries)] for x in range(min(rss_limit, len(queries)))]
        searcher = GoogleNewsRSS()
        for index, query in enumerate(chosen):
            total += 1
            try:
                jobs = searcher.search(query, limit=rss_per_query)
                discovered.extend(jobs)
                if not dry:
                    db.record_source("google_news_rss", True)
            except Exception as error:
                failed += 1
                if not dry:
                    db.record_source("google_news_rss", False, type(error).__name__)
                print(f"[WARN] RSS query {index + 1}: {type(error).__name__}")
    return discovered, total, failed, successful_boards


def scan(db, profile, keywords, discovered, *, dry=False):
    threshold = int(os.getenv("MIN_SCORE", str(profile.get("score_threshold", 65))))
    candidates, rejected, qualified, queued = {}, {}, 0, 0
    for job in discovered:
        fp = job_fp(job)
        if fp in candidates:
            continue
        candidates[fp] = job
    for job in candidates.values():
        outcome = evaluate(job, profile, keywords)
        if outcome.accepted and job.published:
            status = date_status(job, max_age_days=profile.get("max_post_age_days", 21))
            if status != "ok":
                outcome.accepted = False
                outcome.rejection = f"Published date {status}"
        score = outcome.score if outcome.accepted else 0
        rejection = outcome.rejection if not outcome.accepted else (
            "Below relevance threshold" if score < threshold else ""
        )
        if not rejection:
            qualified += 1
        if dry:
            print(f"[PREVIEW] {score:3} {outcome.verification:10} {job.title[:56]} | {rejection or 'QUALIFIED'}")
            continue
        # Persist rejected results as well for audit and dashboard review.
        fp = db.record_opportunity(job, score, outcome.verification, rejection, outcome.reasons)
        if rejection:
            rejected[rejection] = rejected.get(rejection, 0) + 1
            continue
        if db.seen(fp) or db.cluster_alerted(job):
            continue
        db.queue_alert(fp)
        queued += 1
    return len(candidates), qualified, queued, rejected


def deliver(db, token, chat_id, state, *, max_alerts=12, dry=False):
    if dry:
        return 0
    total = 0
    for row in db.pending_alerts(limit=max_alerts):
        try:
            send_alert(token, chat_id, row, with_feedback=bool(state.cipher))
            db.mark_alert_sent(row["fingerprint"])
            # Retain the original dedup database semantics as well.
            from types import SimpleNamespace
            db.add(row["fingerprint"], SimpleNamespace(**row), row["score"], alerted=True)
            total += 1
            print(f"[SENT] {row['score']} | {row['title'][:65]}")
        except Exception as error:
            db.mark_alert_failed(row["fingerprint"], error)
            print(f"[WARN] Notification failed: {type(error).__name__}")
    return total


def maybe_weekly_report(db, token, chat_id, state):
    now = datetime.now(IST)
    if now.weekday() != 0:
        return
    stats = db.stats(days=7)
    counts = {}
    for value in state.data.get("feedback", {}).values():
        counts[value] = counts.get(value, 0) + 1
    feedback_line = (
        f"Feedback (all-time): {counts.get('saved', 0)} saved, "
        f"{counts.get('applied', 0)} applied, "
        f"{counts.get('irrelevant', 0)} marked irrelevant\n"
    ) if state.cipher else ""
    text = (
        "📊 DIP JOB RADAR — weekly report\n"
        f"Discovered: {stats['discovered']} | Eligible: {stats['qualified']} | "
        f"Alerts sent: {stats['alerts_sent']} | Scans: {stats['runs']}\n"
        + feedback_line + "Sources: " + ", ".join(
            f"{x['source']} ({x['ok']} ok/{x['fail']} failed)" for x in stats["sources"][:8]
        )
    )
    try:
        send_once_per_day(db, "weekly_report_" + now.strftime("%G-W%V"), text,
                          token, chat_id, after_hour=9, now=now)
    except Exception as error:
        print(f"[WARN] Weekly report failed: {type(error).__name__}")


def main():
    load_dotenv(ROOT / ".env")
    dry = os.getenv("DRY_RUN", "1") == "1"
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not dry and (not token or not chat_id):
        raise SystemExit("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
    profile, keywords, boards = configuration()
    db = JobDB(":memory:" if dry else ROOT / "data/jobs.sqlite3")
    try:
        # Private data stored encrypted, never as plaintext in a public GitHub repo.
        state = PrivateState(ROOT / "data/private_state.enc")
        if not dry and state.cipher:
            print(f"[FEEDBACK] Processed {receive_feedback(token, chat_id, db, state)} Telegram actions")
        discovered, total, failed, successful_boards = collect(
            db, boards, rss_enabled=os.getenv("RSS_ENABLED", "1") == "1",
            rss_limit=int(os.getenv("RSS_QUERIES_PER_RUN", "12")),
            rss_per_query=int(os.getenv("MAX_RESULTS_PER_QUERY", "12")), dry=dry,
        )
        if total == 0:
            print("[WARN] No sources configured/enabled")
        elif failed == total:
            raise RuntimeError("All enabled job sources failed")
        unique, eligible, queued, rejected = scan(db, profile, keywords, discovered, dry=dry)
        if not dry:
            for source_name, current_ids in successful_boards:
                db.mark_closed_board_jobs(source_name, current_ids)
        sent = deliver(db, token, chat_id, state, max_alerts=int(os.getenv("MAX_ALERTS_PER_RUN", "12")), dry=dry)
        print(f"[RUN] sources={total}, failures={failed}, unique={unique}, eligible={eligible}, queued={queued}, sent={sent}, rejected={sum(rejected.values())}")

        # NEW: Show detailed rejection reasons in GitHub Actions logs.
        print("[REJECTION BREAKDOWN]")
        for reason, count in sorted(rejected.items(), key=lambda item: item[1], reverse=True):
            print(f"[REJECTED] {count} | {reason}")

        if not dry:
            db.record_run(total, failed, unique, eligible, queued)
            if total and failed / total > .5:
                maybe_send_feed_alert(db, token, chat_id, failed, total)
            if os.getenv("SEND_HEARTBEAT", "1") == "1":
                maybe_send_heartbeat(db, token, chat_id, f"{unique} new candidates, {sent} alerts, {failed}/{total} failed sources")
            if os.getenv("WEEKLY_REPORT", "1") == "1":
                maybe_weekly_report(db, token, chat_id, state)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
