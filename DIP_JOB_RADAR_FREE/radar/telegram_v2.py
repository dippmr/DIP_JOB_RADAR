"""Safe Telegram Bot API transport, inline feedback, and opt-in /lead intake."""
from __future__ import annotations

from html import escape

import requests

ACTIONS = {"saved": "💾 Save", "interested": "👍 Interested", "irrelevant": "👎 Not relevant", "applied": "✅ Applied"}


def api(token, method, payload, *, timeout=18, session=None):
    client = session or requests
    try:
        response = client.post(
            f"https://api.telegram.org/bot{token}/{method}", json=payload, timeout=timeout
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError("Telegram API reported failure")
        return data.get("result")
    except requests.RequestException as err:
        status = getattr(getattr(err, "response", None), "status_code", "unknown")
        raise RuntimeError(f"Telegram {method} failed; HTTP {status}") from None


def format_alert(row):
    import json
    reasons = json.loads(row.get("reasons") or "[]")
    link = escape(row.get("apply_url") or row["url"], quote=True)
    verification = {
        "ats": "✅ Published employer ATS listing",
        "employer": "✅ Role-specific employer career page",
    }.get(row["verification"], "⚠️ Unverified hiring lead")
    first = row.get("published") or "Unknown posting date — discovered by Radar"
    return (
        f"🎯 <b>DIP JOB RADAR | {row['score']}/100 relevance</b>\n\n"
        f"<b>{escape(row['title'])}</b>\n"
        f"🏢 {escape(row.get('company') or 'Employer unknown')}\n"
        f"📍 {escape(row.get('location') or 'See listing')}\n"
        f"{verification}\n"
        f"🗓️ {escape(first)}\n"
        f"🌐 {escape(row['source'])}\n\n"
        + "\n".join("• " + escape(r) for r in reasons[:6])
        + f'\n\n🔗 <a href="{link}">Apply / view vacancy</a>'
    )[:4090]


def send_alert(token, chat_id, row, with_feedback=False, session=None):
    payload = {
        "chat_id": chat_id, "text": format_alert(row), "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if with_feedback:
        prefix = row["fingerprint"][:20]
        payload["reply_markup"] = {
            "inline_keyboard": [
                [{"text": label, "callback_data": f"{action}:{prefix}"}]
                for action, label in ACTIONS.items()
            ]
        }
    return api(token, "sendMessage", payload, session=session)


def receive_feedback(token, chat_id, db, state, session=None):
    """Process callbacks and explicit /lead messages from the configured chat only.

    Public post text is NOT written to disk. Only extracted role metadata and
    user-supplied public URL are saved to the review queue, never auto-alerted.
    """
    # getUpdates requires an exclusive consumer; don't use a webhook simultaneously.
    client = session or requests
    offset = int(state.data.get("offset", 0)) if state.cipher else int(db.get_meta("telegram_update_offset") or 0)
    try:
        response = client.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params={"offset": offset, "limit": 100, "timeout": 0, "allowed_updates": '["callback_query","message"]'},
            timeout=15,
        )
        response.raise_for_status()
        response_data = response.json()
        if not response_data.get("ok"):
            raise RuntimeError("Telegram getUpdates returned a non-OK response")
        updates = response_data.get("result", [])
    except (requests.RequestException, ValueError, RuntimeError) as error:
        print(f"[WARN] Telegram feedback poll failed ({type(error).__name__})")
        return 0
    processed = 0
    for update in updates:
        uid = int(update["update_id"])
        message = update.get("message") or {}
        if str((message.get("chat") or {}).get("id", "")) == str(chat_id):
            raw_text = str(message.get("text") or "")
            if raw_text.startswith("/lead "):
                reply = _ingest_lead_command(raw_text, db)
                try:
                    api(token, "sendMessage", {"chat_id": chat_id, "text": reply,
                                               "disable_web_page_preview": True}, session=client)
                except RuntimeError:
                    pass
                processed += 1
        callback = update.get("callback_query") or {}
        if callback:
            in_chat = str((callback.get("message") or {}).get("chat", {}).get("id", ""))
            raw = callback.get("data", "")
            if in_chat == str(chat_id) and ":" in raw:
                action, prefix = raw.split(":", 1)
                if state.cipher and action in ACTIONS and len(prefix) == 20 and all(c in "0123456789abcdef" for c in prefix):
                    rows = db.conn.execute(
                        "SELECT fingerprint FROM opportunities WHERE fingerprint LIKE ? LIMIT 2", (prefix + "%",)
                    ).fetchall()
                    if len(rows) == 1:
                        state.set_feedback(rows[0][0], action)
                        processed += 1
            if callback.get("id"):
                try:
                    api(token, "answerCallbackQuery", {"callback_query_id": callback["id"]}, session=client)
                except RuntimeError:
                    pass
        # Advance only after processing/persisting state, preventing feedback loss.
        offset = max(offset, uid + 1)
        if state.cipher:
            state.data["offset"] = offset
            state.save()
        else:
            db.set_meta("telegram_update_offset", str(offset))
    return processed


def _ingest_lead_command(text, db):
    """Format: /lead HTTPS_URL | Company name | Hiring post text

    This is a manual tip. No scraping, URLs are not fetched, and posts are
    NEVER promoted to independently verified immediate job alerts.
    """
    from urllib.parse import urlsplit, urlunsplit
    from radar.review import review_reason
    from radar.verification import preferred_role_groups
    from search.post_parser import extract_hiring_leads
    from pathlib import Path
    import json

    pieces = text[6:].split("|", 2)
    if len(pieces) != 3:
        return "Usage: /lead https://post-url | Company name | Full public hiring-post text"
    raw_url, company, body = (piece.strip() for piece in pieces)
    if not (2 <= len(company) <= 100 and len(body) >= 20 and len(body) <= 3000):
        return "Lead not saved: provide company name and 20–3000 characters of public hiring text."
    try:
        parsed = urlsplit(raw_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError()
        clean_url = urlunsplit(("https", parsed.hostname.lower(), parsed.path.rstrip("/") or "/", "", ""))
    except ValueError:
        return "Lead not saved: use a public HTTPS post or vacancy URL."
    root = Path(__file__).resolve().parents[1]
    profile = json.loads((root / "config" / "profile.json").read_text(encoding="utf-8"))
    allowed = preferred_role_groups(profile.get("preferred_roles", []))
    found = extract_hiring_leads(body, url=clean_url, source="Telegram submitted public post",
                                 company=company, allowed=allowed)
    reviewed = 0
    for lead in found:
        reason = review_reason(lead, profile)
        if reason:
            db.record_review_lead(lead, reason)
            reviewed += 1
    return (f"Saved {reviewed} unverified relevant hiring lead(s) for daily review. "
            "Not independently verified; no immediate job alert sent."
            if reviewed else "No eligible UI/UX or Product Designer lead with supported location found. Not saved.")
