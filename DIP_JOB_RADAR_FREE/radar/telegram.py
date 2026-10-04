from html import escape
import requests
def format_job(job,scored):
    reasons="\n".join(f"• {escape(x)}" for x in scored.reasons[:6])
    warnings=("\n\n⚠️ "+" | ".join(escape(x) for x in scored.negative_reasons[:3])) if scored.negative_reasons else ""
    return f'🚨 <b>DIP JOB RADAR — {scored.score}/100</b>\n\n<b>{escape(job.title)}</b>\n📍 Ahmedabad\n🌐 {escape(job.source or "Public web result")}\n\n<b>Why it matched</b>\n{reasons or "• Keyword match"}{warnings}\n\n🔗 <a href="{escape(job.url, quote=True)}">Open result</a>'
def send_message(token,chat_id,text):
    r=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",json={"chat_id":chat_id,"text":text,"parse_mode":"HTML","disable_web_page_preview":False},timeout=20); r.raise_for_status()
    data=r.json()
    if not data.get("ok"): raise RuntimeError(f"Telegram API error: {data}")
