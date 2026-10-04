import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from search.web_search import BraveSearch, build_search_queries
from radar.database import JobDatabase
from radar.scoring import score_job
from radar.telegram import format_job, send_message


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def load_keywords():
    with open(ROOT / "config" / "keywords.json", "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    api_key = os.getenv("SEARCH_API_KEY", "").strip()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    api_url = os.getenv(
        "SEARCH_API_URL",
        "https://api.search.brave.com/res/v1/web/search"
    )
    min_score = int(os.getenv("MIN_SCORE", "60"))
    max_results = int(os.getenv("MAX_RESULTS_PER_QUERY", "10"))
    dry_run = os.getenv("DRY_RUN", "0").lower() in {"1", "true", "yes"}

    if not api_key:
        print("ERROR: SEARCH_API_KEY is missing.")
        sys.exit(1)

    if not dry_run and (not bot_token or not chat_id):
        print("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required.")
        sys.exit(1)

    keywords = load_keywords()
    searcher = BraveSearch(api_key, api_url)
    db = JobDatabase()

    queries = build_search_queries(keywords)
    print(f"Running {len(queries)} search queries...")

    candidates = {}
    for index, query in enumerate(queries, 1):
        print(f"[{index}/{len(queries)}] {query}")
        try:
            results = searcher.search(query, count=max_results)
        except Exception as exc:
            print(f"Search error: {exc}")
            continue

        for job in results:
            if not job.url:
                continue
            fp = db.fingerprint(job.url, job.title)
            candidates[fp] = job

    print(f"Unique web results: {len(candidates)}")

    matches = []
    for job in candidates.values():
        if db.seen(job.url, job.title):
            continue

        scored = score_job(job, keywords)

        # Hard Ahmedabad gate.
        text = f"{job.title} {job.description} {job.url}".lower()
        if "ahmedabad" not in text:
            continue

        if scored.score >= min_score:
            matches.append((job, scored))

    matches.sort(key=lambda x: x[1].score, reverse=True)
    print(f"New matches >= {min_score}: {len(matches)}")

    for job, scored in matches:
        message = format_job(job, scored)
        print("\n" + message + "\n")

        if dry_run:
            db.add(job, scored.score, alerted=False)
        else:
            try:
                send_message(bot_token, chat_id, message)
                db.add(job, scored.score, alerted=True)
            except Exception as exc:
                print(f"Telegram error for {job.url}: {exc}")
                # Do not mark as alerted if Telegram failed.

    db.close()


if __name__ == "__main__":
    main()
