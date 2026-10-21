"""Once-per-day Telegram notices: the "alive" heartbeat and feed-failure alerts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from radar.telegram import send_message

IST = timezone(timedelta(hours=5, minutes=30))
HEARTBEAT_HOUR_IST = 9


def send_once_per_day(db, key, text, token, chat_id, after_hour=0, now=None):
    """Send `text` unless it was already sent today (IST). Returns True if sent."""
    now_ist = now or datetime.now(IST)

    if now_ist.hour < after_hour:
        return False

    today = now_ist.strftime("%Y-%m-%d")

    if db.get_meta(key) == today:
        return False

    send_message(token, chat_id, text)
    db.set_meta(key, today)
    return True


def maybe_send_heartbeat(db, token, chat_id, summary, now=None):
    """Daily "alive" message, sent by the first run at/after 9:00 AM IST."""
    try:
        today = (now or datetime.now(IST)).strftime("%Y-%m-%d")
        text = f"DIP JOB RADAR is alive ({today})\nLast run: {summary}"
        sent = send_once_per_day(
            db,
            "last_heartbeat",
            text,
            token,
            chat_id,
            after_hour=HEARTBEAT_HOUR_IST,
            now=now,
        )
        if sent:
            print("[HEARTBEAT] sent")
        return sent
    except Exception as error:
        print(f"[WARN] Heartbeat failed: {error}")
        return False


def maybe_send_feed_alert(db, token, chat_id, failed, total, now=None):
    """Tell the owner (once per day) that many search feeds are failing."""
    try:
        text = (
            f"⚠️ DIP JOB RADAR: {failed} of {total} search feeds failed this run.\n"
            "Google News may be rate-limiting or blocking the bot. "
            "Check the latest run in GitHub Actions."
        )
        sent = send_once_per_day(db, "last_feed_alert", text, token, chat_id, now=now)
        if sent:
            print("[ALERT] feed failure notice sent")
        return sent
    except Exception as error:
        print(f"[WARN] Feed alert failed: {error}")
        return False
