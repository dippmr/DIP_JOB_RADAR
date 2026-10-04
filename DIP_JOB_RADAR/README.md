# DIP JOB RADAR

Personal job-discovery radar for DIP PARMAR.

## Goal

Find publicly searchable Ahmedabad opportunities for:

- UI Designer
- UI/UX Designer
- Junior UI/UX Designer
- Visual Designer
- Junior / Associate Product Designer
- Product Designer (selectively)
- Graphic + UI/UX roles

The radar also searches hiring language and public social/job-post pages, not only formal job listings.

## Architecture

Internet search API -> query expansion -> Ahmedabad filter -> relevance scoring -> SQLite deduplication -> Telegram alert

## Important limitation

This project searches publicly indexed web results. It does **not** log into LinkedIn, bypass LinkedIn protections, scrape private content, or automate applications.

Search coverage depends on the search provider and what that provider indexes.

## Requirements

- GitHub repository
- Python 3.11+
- A web search API key
- A Telegram bot token
- Your Telegram chat ID

## GitHub Secrets

Create these repository secrets:

- `SEARCH_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Optional:

- `SEARCH_API_URL` (defaults to Brave Search API)
- `MIN_SCORE` (defaults to 60)
- `MAX_RESULTS_PER_QUERY` (defaults to 10)

### Search provider

The default implementation uses Brave Search API's web-search endpoint:

`https://api.search.brave.com/res/v1/web/search`

If you use another provider, adapt `search/web_search.py` and keep its output normalized to:

```text
title
url
description
published
source
```

## Local setup

```bash
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install:

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your secrets.

Run:

```bash
python -m radar
```

## Test without Telegram

```bash
DRY_RUN=1 python -m radar
```

## GitHub Actions

The workflow runs hourly.

GitHub scheduled workflows use POSIX cron and normally run in UTC; this workflow uses `timezone: Asia/Kolkata` for the Ahmedabad/India schedule. GitHub documents timezone-aware scheduled workflows. See:
https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax

You can also trigger it manually from Actions -> DIP JOB RADAR -> Run workflow.

## Telegram

The bot uses Telegram's Bot API `sendMessage` method.

Official API:
https://core.telegram.org/bots/api

## Scoring model

Base score: 0

Positive signals:

- Ahmedabad: +30
- Primary target role: +25
- Strong UI/UX/product phrase: +20
- Figma: +10
- UX/product skill: +5
- Hiring language: +10
- Recent publication: +5
- Public post/social hiring signal: +5

Negative signals:

- Outside Ahmedabad: -50
- Senior/Lead/Manager: -30
- Internship/Trainee: -30
- Purely unrelated design role: -25
- Video/3D-only role: -25
- UX research-only: -25

Alert threshold: 60.

The score is intentionally conservative. Review the original posting before applying.

## State / deduplication

`data/jobs.sqlite3` stores normalized URLs and fingerprints.

The workflow commits database changes back to the repository so future hourly runs remember what was already alerted.

Do not store API tokens in the database.

## Keyword database

Edit `config/keywords.json` to tune the search.

The default keyword set is intentionally broader than only "UI/UX Designer" because recruiters may use:

- "we're hiring"
- "looking for a designer"
- "join our design team"
- Figma
- product design
- interface design
- visual design

## Security

Never put secrets directly in source files.

Use GitHub Actions Secrets for production.
