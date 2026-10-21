# DIP JOB RADAR V2

A Python + GitHub Actions + SQLite + Telegram job-discovery project for Ahmedabad-area UI/UX and design vacancies. V2 retains the original `DIP_JOB_RADAR_FREE/radar/__main__.py` code and existing database, but the **new recommended scanner is `python -m radar.v2`**.

> **Deployment status:** All automated tests run without live ATS/Telegram credentials. To receive **verified** job alerts, you must configure real companies in `config/company_watchlist.json`. The watchlist starts empty intentionally; the project does not invent company job-board accounts. RSS leads remain discoverable in the database/dashboard, but are **not sent as verified jobs** by default.

## What's new — all 12 planned improvements

| # | Improvement | V2 implementation / important qualification |
|---|---|---|
| 1 | Vacancy verification | Rejects courses, search-results pages, non-design roles, excluded seniority and excessive experience requirements. ATS jobs count as published listings, **not** guaranteed available by the time you apply. |
| 2 | Multi-source search | Public Greenhouse / Lever / Ashby job boards, plus rotating Google News RSS. Company-specific board tokens must be configured. |
| 3 | Intelligent matching | Explainable, customizable role / skills / location / experience scoring, with hard rejection gates. Rule-based; **no paid AI or invented fit percentage**. |
| 4 | Company watchlist | `config/company_watchlist.json` with company, provider, board token and optional Lever region. |
| 5 | Candidate preferences | `config/profile.json`: preferred roles/skills/cities, seniority, remote India, hybrid, excluded employers and alert threshold. Salary floor is a future enhancement; it is **not enforced** without verified salary fields. |
| 6 | Direct application links | ATS `applyUrl` / `absolute_url`; Telegram shows a link to the listing/application page. |
| 7 | Dedup + freshness | Stable ATS IDs, company/title/location heuristic across sources, published-date checks when available, discovered timestamps, and `not_seen_on_board` for removed ATS listings. |
| 8 | Telegram interaction | Save, Interested, Not relevant, Applied buttons. Feedback polling only when `RADAR_STATE_KEY` is configured. Status is encrypted before GitHub commit. |
| 9 | Job dashboard | Read-only local browser dashboard with filters, scores, source breakdown and (with key) personal status. Not a hosted public app. |
| 10 | Analytics / weekly report | Source-health history, 7-day counts and Monday Telegram report at/after 09:00 IST. |
| 11 | Reliability | GitHub tests, 5-attempt notification queue, feed-failure alert, daily heartbeat, encrypted personal state, SQLite consistent backups via GitHub artifact. |
| 12 | Application prep helper | Generates a real-job-specific checklist, skill review and editable application/follow-up drafts. **No auto-apply and no invented resume credentials.** |

## Quick start

1. Unzip, open the `DIP_JOB_RADAR_FREE` folder and install prerequisites:
   ```bash
   python -m pip install -r requirements.txt pytest
   ```
2. Edit `config/profile.json` to reflect your real target job profile.
3. Add legitimate company board identifiers to `config/company_watchlist.json`. Example (**replace with verified real employers**):
   ```json
   {"boards": [
     {"company": "Your Confirmed Company", "provider": "greenhouse", "token": "confirmed-board-id", "enabled": true},
     {"company": "Another Confirmed Company", "provider": "lever", "token": "confirmed-site-id", "enabled": true, "region": "global"},
     {"company": "Third Confirmed Company", "provider": "ashby", "token": "confirmed-job-board-name", "enabled": true}
   ]}
   ```
   **Do not paste a whole URL** into `token`. For Greenhouse use the segment after `boards.greenhouse.io/` or the actual API board token; Lever uses the site name after `jobs.lever.co/`, and Ashby uses the segment after `jobs.ashbyhq.com/`.
4. Dry-run without Telegram or writes:
   ```bash
   DRY_RUN=1 python -m radar.v2
   ```
   On Windows PowerShell: `$env:DRY_RUN='1'; python -m radar.v2`.
5. Create your Telegram bot via **@BotFather**, start a private conversation with it, then add GitHub **Actions secrets**: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
6. For encrypted Telegram feedback, generate a unique key locally:
   ```bash
   python -m radar.keygen
   ```
   Add the value as a third GitHub Actions secret: **`RADAR_STATE_KEY`**. Store a backup securely. **If this key is lost, encrypted feedback cannot be recovered.** Never commit the key. Never change it without migrating/encrypting the existing state.
7. Push the new project to the existing GitHub repository (prefer a backup branch and PR), check `Actions > Radar tests`, then manually run `Actions > DIP JOB RADAR V2 > Run workflow`. Production GitHub Actions uses `DRY_RUN=0`.

**Important:** Adding the ZIP contents does not change your GitHub repository automatically. You must commit/push the files. Keep the existing database (`data/jobs.sqlite3`) to retain deduplication history.

## Local dashboard and application prep

```bash
cd DIP_JOB_RADAR_FREE
python -m radar.dashboard
# Open http://127.0.0.1:8765 in your browser
```

The dashboard is read-only and bound to `127.0.0.1`. To generate a manual application checklist for a particular job, copy its fingerprint from the DB/API and run:

```bash
python -m radar.assistant <fingerprint-prefix> --output my_application_draft.txt
```

Telegram feedback is only processed by the scheduled scanner with a state key. Do not configure Telegram webhooks or a second bot using `getUpdates` for the same token, or Telegram callbacks may conflict.

## Configuration and transparency

| Setting | Default | Notes |
|---|---|---|
| `DRY_RUN` | `1` locally, `0` in Actions | Preview without persisting or sending |
| `MIN_SCORE` | `65` | Minimum relevance score, **not** a probability |
| `RSS_QUERIES_PER_RUN` | `12` | Rotates original 46 queries each scheduled run |
| `MAX_RESULTS_PER_QUERY` | `12` | RSS read limit |
| `MAX_ALERTS_PER_RUN` | `12` | Limits Telegram flood |
| `RSS_ENABLED` | `1` | Set `0` to only use company boards |
| `SEND_HEARTBEAT` | `1` | Daily after 09:00 IST |
| `WEEKLY_REPORT` | `1` | Mondays after 09:00 IST |

**Publication date ≠ discovery date.** Lever created timestamps may be available; Greenhouse `updated_at` is intentionally not treated as posting date. ATS jobs without reliable publication date may still be active and eligible; Telegram labels this accurately. Google News dates refer to the RSS story, not necessarily the vacancy.

**“Verified ATS listing” only means the listing was returned by a published public board at scan time.** It does not verify the employer's trustworthiness, salary, vacancy eligibility, or that a job remains open indefinitely. Always confirm with the employer before submitting personal information.

**Deduplication is heuristic across different ATS sources.** Jobs with the same company + title + city are grouped; this may group legitimate multiple openings. A stable ATS posting ID is always retained for source-specific identification.

**Data privacy:** The original `data/jobs.sqlite3` remains in this *public* GitHub repository and contains URLs, scores and job history visible to anyone. Never store a resume, personal contact details, private compensation expectations, or chat IDs there. Personal feedback/status is only stored in encrypted `data/private_state.enc` when `RADAR_STATE_KEY` is configured. Encryption does not hide metadata such as commit timing or encrypted file size. The local dashboard must not be internet-exposed. For stronger privacy, make your repository **private**.

**Notifications:** Alerts are queued in SQLite before being delivered. If Telegram succeeds but the process crashes before marking a message sent, a duplicate alert may occur; Telegram does not provide a general idempotent send key. Failed alerts retry up to five scans.

**Costs:** This project doesn't require paid AI APIs. GitHub Actions runtime, artifact retention, and third-party API limits are subject to provider terms and plan limits. Scheduled jobs may be delayed, so 15 minutes is a requested cadence, not a guaranteed arrival time.

## Validation

```bash
cd DIP_JOB_RADAR_FREE
python -m pytest -q
python -m radar.backup
```

The backup is created in `tmp/backup/` and excluded from git. GitHub Actions uploads a short-lived artifact (7 days). The SQL source of truth remains `data/jobs.sqlite3` in git. Private feedback cannot be decrypted without your key.

## Public API documentation

- Greenhouse: https://docs.greenhouse.io/job-board
- Lever: https://github.com/lever/postings-api
- Ashby: https://developers.ashbyhq.com/docs/public-job-posting-api
- Telegram: https://core.telegram.org/bots/api

## Limitations / future enhancements

- ATS coverage is limited to **configured company boards**; do not expect city-wide comprehensive coverage.
- RSS results are unverified and **not alerted** by default. You can set `allow_unverified_rss` to `true` in `config/profile.json` to receive clearly labeled *leads*, but expect more false positives.
- Scraping restricted LinkedIn/Indeed/Naukri pages and submitting job applications automatically are deliberately **not implemented**.
- Salary-based filtering and automatic extraction of unstructured location/experience are not yet reliable enough for mandatory filtering. Check employer descriptions manually.
- The dashboard is local-only and read-only; feedback actions are taken in Telegram. This prevents accidentally publishing personal application status.
- AI/LLM scoring is intentionally optional/not implemented; V2 uses transparent rules. An LLM can be integrated later with privacy controls.
