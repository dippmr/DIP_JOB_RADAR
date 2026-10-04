# DIP JOB RADAR — FREE EDITION

A free public-source job radar for DIP PARMAR.

## What it does
- No Brave Search API
- No paid search API
- No search API key
- Uses public RSS/search feeds
- Searches Ahmedabad UI/UX, Visual Design and Product Design opportunities
- Scores and deduplicates results
- Sends matches to your Telegram bot
- Runs hourly with GitHub Actions

## Limitation
This is not literally the entire internet. It monitors public RSS/search feeds. Some websites, including LinkedIn, may not expose every public post through RSS/search. It does not log in, bypass protections, scrape private content, or apply to jobs.

## Required GitHub Secrets
Only:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

There is NO SEARCH_API_KEY.

## Local dry run
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DRY_RUN="1"
python -m radar
```
Dry run does not send Telegram messages or modify the duplicate database.

## GitHub
Upload the project. Add the two Telegram secrets under Settings → Secrets and variables → Actions. Then Actions → DIP JOB RADAR FREE → Run workflow.

The workflow is scheduled at minute 17 of every hour in Asia/Kolkata. GitHub supports scheduled workflows and timezone-aware cron; schedules can be delayed during high load, so minute 17 avoids the top of the hour.

## Security
Never commit the Telegram token. Use GitHub Actions Secrets.

## Free means
No paid search API is required. GitHub/service limits and public-source availability still apply.
