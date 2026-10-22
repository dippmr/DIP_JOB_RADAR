# DIP JOB RADAR V2 — smart Telegram notification update

This update uses the **existing cron-job.org 15-minute API dispatch**. It does not add a new scheduler or modify the existing Telegram bot credentials.

## New notification policy

- Each successful scan: **silent**, except immediate job alerts already sent by `radar.v2`.
- First and second consecutive unsuccessful workflow runs: silent (recorded in `data/monitor_state.json`).
- Third consecutive unsuccessful workflow run: send **one Telegram warning**, no further warning until a successful run resets the streak. If sending fails, it retries on the next unsuccessful run.
- One daily summary: first successful scan **at or after 9:00 PM IST**, with counts through that scan. No summary if the scanner is still failing; it will try again after recovery on the same day.
- No separate daily heartbeat, weekly report or once-per-day feed-failure alert.

## Upload exactly these files to the corresponding repository paths

1. `.github/workflows/main.yml` — REPLACE the existing file.
2. `DIP_JOB_RADAR_FREE/radar/v2.py` — REPLACE the existing file.
3. `DIP_JOB_RADAR_FREE/radar/smart_notifications.py` — CREATE this new file.
4. `DIP_JOB_RADAR_FREE/tests/test_smart_notifications.py` — CREATE this new test file (recommended).

Use the **changed-files ZIP** if you only want the four files, or the full repository ZIP for an entire updated copy. In GitHub's web interface, create/edit each file under its exact directory. DO NOT upload the ZIP as a file into the repository.

## Test

1. Commit all four changes on the `main` branch.
2. Open GitHub > Actions > DIP JOB RADAR V2 > Run workflow and confirm the run succeeds.
3. In the GitHub log, check the `Smart Telegram notifications` step for `notifications=none` on normal scans outside the daily-report window.
4. The step automatically creates `DIP_JOB_RADAR_FREE/data/monitor_state.json` on its first run and commits the file. It contains nonsensitive counters, dates and a run identifier.
5. Keep cron-job.org configured with the original 15-minute dispatch URL ending in `/actions/workflows/main.yml/dispatches`; NO changes needed there.

## Important limitations

- One daily report means the first *successful* scan at or after 9 PM IST, not a precisely timed 9:00 PM notification. It shows statistics accumulated **so far that day**. If no run succeeds before midnight, there is no summary for that day.
- Failure streaks cover failures of steps **before** the `Smart Telegram notifications` step. They cannot count checkout failures, cancellation, the notification step itself, a later git push failure, or a GitHub run that is never started.
- If the monitor step cannot run or push its state, streak tracking is unavailable for that run. Cron-job.org monitoring is still useful to detect missed triggers.
- As with other GitHub Actions artifacts, bot token and chat ID must already exist in repository secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
- Ensure both ZIPs are reviewed before using in your repository. Your existing SQLite database stays intact and unchanged in the distribution ZIP.
