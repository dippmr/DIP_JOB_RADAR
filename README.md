[README.md](https://github.com/user-attachments/files/33755205/README.md)
# DIP JOB RADAR

A free, automated job-alert bot for **UI/UX and Product Design roles in Ahmedabad, Gujarat**. It searches public feeds, filters out old or irrelevant posts, removes duplicates, scores relevance, and sends matches to **Telegram**. It runs on **GitHub Actions**, so there is no server and no paid API.

---

## Features

- Searches Google News RSS with 46 Ahmedabad-focused design-hiring queries
- Freshness filter: only posts from the last 7-14 days
- Ahmedabad location check
- Relevance scoring against target roles, with exclusions (senior/lead, intern, video-only, motion-only, 3D, architecture, fashion, interior, UX-research-only)
- SQLite duplicate protection, so the same job is never sent twice
- Telegram alerts, plus a **daily "alive" message** so silence never means a broken bot
- Per-run summary log showing where every result was filtered out

---

## How it works

| Step | What happens |
|---|---|
| 1. Collect | Runs every query against Google News RSS (with a `when:7d` time filter) |
| 2. Deduplicate | Merges identical results using a title + URL fingerprint |
| 3. Date filter | Drops results that are old, missing a date, or dated in the future |
| 4. Seen check | Skips jobs already stored in `data/jobs.sqlite3` |
| 5. Location | Keeps results that mention Ahmedabad |
| 6. Score | Scores each job from 0-100 against `config/keywords.json` |
| 7. Send | Matches at or above `MIN_SCORE` are sent to Telegram and saved to the database |
| 8. Commit | The updated database is committed back to `main` |

---

## Repository structure

```text
.github/workflows/main.yml     Scheduled workflow (every 15 min + manual run)
DIP_JOB_RADAR/                 Old Brave Search version (archived, do not edit)
DIP_JOB_RADAR_FREE/            Current free version
  config/keywords.json         Target roles, include and exclude keywords
  radar/__main__.py            Main pipeline
  radar/database.py            SQLite storage and fingerprints
  radar/scoring.py             Relevance scoring
  radar/telegram.py            Telegram formatting and sending
  search/rss_search.py         Google News RSS searcher and queries
  tests/                       Tests
  data/jobs.sqlite3            Duplicate database (committed by the workflow)
  requirements.txt
```

---

## Setup

1. Create a Telegram bot with **@BotFather** and copy the bot token.
2. Get your chat ID (message your bot, then check `getUpdates`).
3. In GitHub: **Settings → Secrets and variables → Actions → New repository secret**, then add:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. Go to **Actions → DIP JOB RADAR FREE → Run workflow** to test.

> Never commit tokens, chat IDs, or a `.env` file. Secrets belong only in GitHub Actions secrets.

---

## Configuration

Set in the workflow's `env` block in `.github/workflows/main.yml`:

| Variable | Default | Purpose |
|---|---|---|
| `MIN_SCORE` | `60` | Minimum score (0-100) to send an alert |
| `MAX_RESULTS_PER_QUERY` | `15` | Results read per search query |
| `FRESH_WINDOW` | `7d` | Google News time filter (`1d`, `7d`, `14d`) |
| `DRY_RUN` | `0` | `1` prints matches only, with no Telegram and no database writes |

The date filter is set by `MAX_JOB_AGE_DAYS` (14) in `radar/__main__.py`. Target roles and exclusions are in `config/keywords.json`.

---

## Run locally

```bash
cd DIP_JOB_RADAR_FREE
pip install -r requirements.txt
DRY_RUN=1 python -m radar
```

Create a local `.env` (git-ignored) with the Telegram values only if you test real sending.

---

## Reading the run log

Each run prints one summary line in **Actions → run → Run radar**:

```text
Queries: 46 | Unique results: 171 | Skipped old/unknown dates: 146 (...) |
Skipped location: 14 | Skipped duplicates: 0 | Below score 60: 11 | Matches: 0
```

| Field | Meaning |
|---|---|
| Unique results | Results collected after merging duplicates |
| Skipped old/unknown dates | Results older than the window, or with a missing or invalid date |
| Skipped location | Results that don't mention Ahmedabad |
| Skipped duplicates | Jobs already sent before |
| Below score | Fresh Ahmedabad jobs that scored under `MIN_SCORE` |
| `[LOW SCORE]` lines | The best near-misses, with score and title |
| Matches | Alerts sent this run |

---

## Daily heartbeat

The first run at or after 9:00 AM IST each day sends a Telegram message: "DIP JOB RADAR is alive", with a short summary of the last run. If it stops arriving, check the Actions tab.

---

## Troubleshooting

| Problem | Check |
|---|---|
| No runs appearing | The workflow file must start with a valid `on:` block; check Actions for "Invalid workflow file" |
| Runs are hours apart | GitHub delays scheduled runs on free accounts; this is normal |
| No alerts for days | Read the summary line: mostly "old" means the source is stale; "below score" means the threshold may be too strict |
| Telegram error 404 | The bot token secret is wrong or has extra spaces |
| Telegram error 400 | The chat ID is wrong, or you haven't messaged the bot yet |
| Database push fails | Workflow needs `permissions: contents: write` |

---

## Roadmap

- [x] 14-day freshness filter
- [x] Daily heartbeat message
- [x] Skip-reason breakdown in logs
- [ ] Stricter Ahmedabad location verification
- [ ] Extra sources with real posting dates (job-board feeds, company career pages)
- [ ] Tune scoring using the `[LOW SCORE]` logs

---

## Notes

- Google News indexes news, not job boards, so expect a small number of fresh matches.
- The repository is public, so the database and code are visible. Keep personal data out of it.
