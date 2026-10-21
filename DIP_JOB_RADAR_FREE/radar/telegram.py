"""Telegram message formatting and sending."""

from __future__ import annotations

from html import escape

import requests

from radar.scoring import LOCATION_STRONG


def format_job(job, scored):
    reasons = "\n".join(f"• {escape(x)}" for x in scored.reasons[:6])

    warnings = ""
    if scored.negative_reasons:
        warnings = "\n\n⚠️ " + " | ".join(
            escape(x) for x in scored.negative_reasons[:3]
        )

    if scored.location == LOCATION_STRONG:
        place = "📍 Ahmedabad"
    else:
        place = "📍 Ahmedabad (found by search only, please verify)"

    source = escape(job.source or "Public web result")
    link = escape(job.url, quote=True)

    return (
        f"🚨 <b>DIP JOB RADAR — {scored.score}/100</b>\n\n"
        f"<b>{escape(job.title)}</b>\n"
        f"{place}\n"
        f"🌐 {source}\n\n"
        f"<b>Why it matched</b>\n{reasons or '• Keyword match'}{warnings}\n\n"
        f'🔗 <a href="{link}">Open result</a>'
    )


def send_message(token, chat_id, text):
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        # The default error text contains the request URL, which contains the
        # bot token. Report only the status so the token never reaches a log.
        status = getattr(getattr(error, "response", None), "status_code", "n/a")
        raise RuntimeError(
            f"Telegram request failed (HTTP {status}, {type(error).__name__})"
        ) from None

    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
