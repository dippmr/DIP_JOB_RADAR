import requests
from html import escape


def format_job(job, scored) -> str:
    reasons = ", ".join(scored.reasons[:5]) or "keyword match"
    negatives = ", ".join(scored.negative_reasons[:3])

    parts = [
        f"<b>🚨 DIP JOB RADAR — {scored.score}/100</b>",
        "",
        f"<b>{escape(job.title)}</b>",
        f"📍 Ahmedabad",
        f"🌐 {escape(job.source or 'Web')}",
        "",
        f"<b>Why it matched:</b> {escape(reasons)}",
    ]

    if negatives:
        parts.append(f"⚠️ <b>Check:</b> {escape(negatives)}")

    parts += [
        "",
        f"🔗 <a href=\"{escape(job.url, quote=True)}\">Open job / original post</a>"
    ]

    return "\n".join(parts)


def send_message(bot_token: str, chat_id: str, message: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=30,
    )
    response.raise_for_status()
