from __future__ import annotations
import json, os
from pathlib import Path
from dotenv import load_dotenv
from search.rss_search import GoogleNewsRSS, build_queries
from radar.database import JobDB, fingerprint
from radar.scoring import score_job
from radar.telegram import format_job, send_message
ROOT=Path(__file__).resolve().parents[1]
def main():
    load_dotenv(ROOT/".env")
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip(); chat_id=os.getenv("TELEGRAM_CHAT_ID","").strip(); dry=os.getenv("DRY_RUN","1").strip()=="1"; threshold=int(os.getenv("MIN_SCORE","60")); limit=int(os.getenv("MAX_RESULTS_PER_QUERY","15"))
    if not dry and (not token or not chat_id): raise SystemExit("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
    keywords=json.loads((ROOT/"config/keywords.json").read_text(encoding="utf-8")); db=JobDB(ROOT/"data/jobs.sqlite3"); searcher=GoogleNewsRSS(); all_jobs={}; queries=build_queries()
    for q in queries:
        try:
            for job in searcher.search(q,limit): all_jobs.setdefault(fingerprint(job.url,job.title),job)
        except Exception as e: print(f"[WARN] Feed failed: {q} :: {e}")
    matches=[]
    for fp,job in all_jobs.items():
        if not dry and db.seen(fp): continue
        if "ahmedabad" not in f"{job.title} {job.description} {job.url}".lower(): continue
        scored=score_job(job,keywords)
        if scored.score>=threshold: matches.append((fp,job,scored))
    matches.sort(key=lambda x:x[2].score,reverse=True)
    print(f"Queries: {len(queries)} | Unique results: {len(all_jobs)} | Matches: {len(matches)}")
    for fp,job,scored in matches[:20]:
        if dry:
            print(f"\n--- DRY RUN {scored.score}/100 ---\n{job.title}\n{job.url}\n"+"\n".join(scored.reasons))
        else:
            try: send_message(token,chat_id,format_job(job,scored)); db.add(fp,job,scored.score,True); print(f"[SENT] {scored.score} | {job.title}")
            except Exception as e: print(f"[ERROR] Telegram send failed: {e}")
    db.close()
if __name__=="__main__": main()
