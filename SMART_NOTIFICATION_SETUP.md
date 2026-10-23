# DIP JOB RADAR V2 — notification repair (23 October 2026)

## What changed

The existing `.github/workflows/main.yml` accidentally sent a Telegram message **after every workflow run** despite the project already containing `radar/smart_notifications.py`. This repair removes that per-run message and **runs the existing smart monitor** instead. It also disables the older heartbeat, optional weekly report, and high-feed-failure message in the scheduled workflow to avoid surprise status notifications.

The workflow **still runs on GitHub `workflow_dispatch` only**. Your existing cron-job.org trigger (every 15 minutes) remains unchanged. Do not add a GitHub `schedule` trigger; that would run duplicate scans.

## Telegram policy after deploying

- Every healthy 15-minute scan: **no status message**.
- Newly eligible and previously unalerted verified jobs: **immediate Telegram job alert** (unchanged).
- Daily status summary: **once on the first successful scan after 21:00 IST**. This is *not* guaranteed exactly at 21:00.
- Workflow failures: **one warning after the third consecutive failing run**; it does not repeat throughout the same failure streak. Source fetch failures alone do not constitute workflow failures unless the scan stops.
- Neither the weekly report nor daily heartbeat is enabled in this GitHub workflow.

The monitor creates `DIP_JOB_RADAR_FREE/data/monitor_state.json` containing only counters and dates. The workflow commits it to `main` after each run so the summary is not re-sent. GitHub Actions must have `contents: write` permissions and the repository secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` must remain configured.

## How to deploy

**Recommended:** Use `DIP_JOB_RADAR_notification_fix_2026-10-23.zip` for only the changed files. Extract it, then upload/create the files *at the exact same paths* on your repo's `main` branch:

1. `.github/workflows/main.yml` — replace this file.
2. `DIP_JOB_RADAR_FREE/tests/test_workflow_notification_policy.py` — add this regression test.
3. `SMART_NOTIFICATION_SETUP.md` — replace the instructions (optional for runtime).
4. `AUDIT_REPORT_2026-10-23.md` — optional audit reference.

Do **not** upload the ZIP itself to the repo, and do not replace `data/jobs.sqlite3` from an older full-repo archive. No Python production-code changes are required: `radar/smart_notifications.py` is already present and its tests were passing.

To validate: GitHub > Actions > DIP JOB RADAR V2 > Run workflow. The step `Smart Telegram monitor (daily summary / failure warning)` should show `notifications=none` for an ordinary daytime healthy run. Afterward check that `data/monitor_state.json` is present in the repository and the workflow completes successfully. A normal run will still process jobs and may send alerts for **new qualified openings**.

## Coverage limitations (unfixed by notifications)

- `search/platform_discovery.py` searches Google News RSS for site-targeted **LinkedIn `/jobs` listings**, not live LinkedIn member posts. Google News indexing is incomplete. The repository does not have a direct LinkedIn Posts integration.
- `config/manual_career_pages.json` is a reference list and is not scanned automatically.
- `config/profile.json` has `allow_unverified_rss: false`, so RSS/social leads are rejected from automated job alerts unless independently verified. This is an intentional safety/precision trade-off; changing it may create false-positive alerts.
- This repair **does not promise** to detect the Pixster Studio hiring announcement. A separate discovery and verification design would be required.

## Monitoring limitations

If no run completes successfully after 21:00 IST and before midnight, no daily message will be sent for that day. Checkout failures, cancellation, missing dispatches, and git-push failures cannot reliably be tracked by the in-workflow monitor; inspect GitHub Actions / cron-job.org separately. A failed git push can prevent persisting the day's monitor state. The daily report's reviewed count sums candidates seen across scans, not distinct jobs.
