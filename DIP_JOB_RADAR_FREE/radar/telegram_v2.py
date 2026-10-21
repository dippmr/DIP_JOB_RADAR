"""Safe Telegram Bot API transport, inline feedback, and cursor polling."""
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
    verification = "✅ Published ATS listing" if row["verification"] == "ats" else "⚠️ Unverified RSS hiring lead"
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
    """Reads only this bot's feedback; never process messages from other chats."""
    if not state.cipher:
        return 0
    # getUpdates requires an exclusive consumer; don't use a webhook simultaneously.
    client = session or requests
    offset = int(state.data.get("offset", 0))
    try:
        response = client.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params={"offset": offset, "limit": 100, "timeout": 0, "allowed_updates": '["callback_query"]'},
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
        callback = update.get("callback_query") or {}
        if callback:
            in_chat = str((callback.get("message") or {}).get("chat", {}).get("id", ""))
            raw = callback.get("data", "")
            if in_chat == str(chat_id) and ":" in raw:
                action, prefix = raw.split(":", 1)
                if action in ACTIONS and len(prefix) == 20 and all(c in "0123456789abcdef" for c in prefix):
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
        state.data["offset"] = max(offset, uid + 1)
        state.save()
    return processed
