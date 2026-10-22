"""Telegram smart notifications for GitHub Actions.

Called exactly once at the end of each scheduled workflow run (before committing
state), independent of radar.v2. No message is sent on an ordinary healthy scan.

- Immediate eligible-job alerts remain the responsibility of radar.v2.
- Warn once when a streak FIRST reaches three failed workflow runs.
- Send one daily summary on the first successful run at/after 21:00 IST.

All state is stored in a small public JSON file that is committed to main by the
workflow; it contains counters/dates only, never Telegram credentials.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data/monitor_state.json"
DB_PATH = ROOT / "data/jobs.sqlite3"
IST = timezone(timedelta(hours=5, minutes=30))


def initial_state():
    return {
        "consecutive_failures": 0,
        "failure_warning_sent": False,
        "last_daily_report_ist": "",
        "daily_workflows": {},
        "last_run_identifier": "",
    }


def load_state(path=STATE_PATH):
    state = initial_state()
    if path.exists():
        incoming = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(incoming, dict):
            raise ValueError("Monitor state must be a JSON object")
        state.update({k: incoming[k] for k in state if k in incoming})
    return state


def write_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write; no credentials enter this file.
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix=".monitor-", suffix=".tmp", delete=False
    ) as out:
        json.dump(state, out, indent=2, sort_keys=True)
        out.write("\n")
        temp_name = out.name
    os.replace(temp_name, path)


def send_telegram(text, token, chat_id):
    if not token or not chat_id:
        print("[MONITOR] Telegram secrets absent; message not sent")
        return False
    data = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            answer = json.load(response)
        if not answer.get("ok"):
            raise ValueError("Telegram returned ok=false")
    except Exception as exc:
        # Do not log `exc`: urllib exceptions can contain the secret bot-token URL.
        print(f"[MONITOR] Telegram delivery failed: {type(exc).__name__}")
        return False
    return True


def daily_statistics(db_path, day):
    """Count the calendar day in IST; SQLite CURRENT_TIMESTAMP is UTC."""
    start = datetime.combine(day, time.min, tzinfo=IST).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    a, b = (dt.strftime("%Y-%m-%d %H:%M:%S") for dt in (start, end))
    with sqlite3.connect(db_path) as db:
        completed, reviewed, source_failures = db.execute(
            """SELECT COUNT(*), COALESCE(SUM(discovered),0),
                      COALESCE(SUM(failures),0)
               FROM scan_runs WHERE run_at >= ? AND run_at < ?""", (a, b)
        ).fetchone()
        newly_eligible = db.execute(
            """SELECT COUNT(*) FROM opportunities
               WHERE first_seen_at >= ? AND first_seen_at < ?
               AND rejection_reason = ''""", (a, b)
        ).fetchone()[0]
        alerts_sent = db.execute(
            """SELECT COUNT(*) FROM notification_queue
               WHERE sent_at >= ? AND sent_at < ?""", (a, b)
        ).fetchone()[0]
    return {
        "completed": completed,
        "reviewed": reviewed,
        "source_failures": source_failures,
        "newly_eligible": newly_eligible,
        "alerts_sent": alerts_sent,
    }


def github_run_url():
    repo = os.environ.get("GITHUB_REPOSITORY", "dippmr/DIP_JOB_RADAR")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    return f"https://github.com/{repo}/actions/runs/{run_id}" if run_id else f"https://github.com/{repo}/actions"


def process(state, *, success, now, run_identifier, send, stats=None, run_link=""):
    """Pure-ish state transition, injected send/stats for offline tests."""
    today = now.date().isoformat()
    # Avoid double-counting the same attempt if the command is rerun.
    if run_identifier and run_identifier == state.get("last_run_identifier"):
        return state, []
    state["last_run_identifier"] = run_identifier
    counters = state.setdefault("daily_workflows", {})
    counts = counters.setdefault(today, {"executions": 0, "failed": 0})
    counts["executions"] += 1
    sent = []
    if success:
        state["consecutive_failures"] = 0
        state["failure_warning_sent"] = False
    else:
        counts["failed"] += 1
        state["consecutive_failures"] += 1
        if state["consecutive_failures"] >= 3 and not state["failure_warning_sent"]:
            txt = (
                "🚨 DIP JOB RADAR V2 — Scanner warning\n"
                f"❌ {state['consecutive_failures']} consecutive workflow runs failed\n"
                f"🕒 {now.strftime('%d %b %Y, %I:%M %p')} IST\n"
                "🔍 Check the GitHub Actions logs:\n"
                f"{run_link}"
            )
            if send(txt):
                state["failure_warning_sent"] = True
                sent.append("three-failure warning")
    # The summary waits for the first successful scan at/after 9:00 PM IST.
    if (success and now.hour >= 21 and state.get("last_daily_report_ist") != today):
        if stats is None:
            print("[MONITOR] Daily summary postponed: no scan database available")
        else:
            txt = (
                "📊 DIP JOB RADAR V2 — Daily Report (today so far)\n"
                f"📅 {now.strftime('%d %b %Y')} (IST)\n"
                f"✅ Completed scans: {stats['completed']}\n"
                f"⚠️ Failed workflow runs: {counts['failed']}\n"
                f"🔎 Candidates reviewed (across scans): {stats['reviewed']}\n"
                f"🎯 New eligible jobs discovered: {stats['newly_eligible']}\n"
                f"🔔 Relevant job alerts sent: {stats['alerts_sent']}\n"
                f"🌐 Source fetch failures: {stats['source_failures']}\n"
                f"🔗 {run_link}"
            )
            if send(txt):
                state["last_daily_report_ist"] = today
                sent.append("daily summary")
    # Only keep three calendar days of nonsensitive monitor counts.
    for key in list(counters):
        if key < (now.date() - timedelta(days=2)).isoformat():
            del counters[key]
    return state, sent


def main():
    state = load_state()
    status = os.environ.get("RADAR_WORKFLOW_STATUS", "").lower()
    scan_status = os.environ.get("RADAR_SCAN_STATUS", "").lower()
    success = status == "success" and scan_status == "success"
    now = datetime.now(IST)
    run_identifier = (
        f"{os.environ.get('GITHUB_RUN_ID', '')}:"
        f"{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
    )
    db_stats = None
    if success and now.hour >= 21 and state["last_daily_report_ist"] != now.date().isoformat():
        try:
            db_stats = daily_statistics(DB_PATH, now.date())
        except (OSError, sqlite3.Error) as exc:
            print(f"[MONITOR] Cannot read daily totals: {type(exc).__name__}")
    state, notifications = process(
        state, success=success, now=now, run_identifier=run_identifier,
        send=lambda msg: send_telegram(
            msg, os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        ), stats=db_stats, run_link=github_run_url(),
    )
    write_state(STATE_PATH, state)
    print(f"[MONITOR] scan_success={success} failure_streak={state['consecutive_failures']} "
          f"notifications={','.join(notifications) if notifications else 'none'}")


if __name__ == "__main__":
    main()
