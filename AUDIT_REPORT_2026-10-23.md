# DIP JOB RADAR — audit of uploaded ZIP (23 October 2026)

**Scope:** Inspected local uploaded source code, workflow, scanner settings and stored SQLite scan history. No live GitHub, cron-job.org, LinkedIn, or Telegram credentials were accessed.

| Check | Evidence in uploaded ZIP | Finding |
|---|---|---|
| Telegram every 15 minutes | `.github/workflows/main.yml` contained `Notify Telegram after every run` with `if: always()` | **Confirmed bug. Fixed in this distribution.** |
| Smart daily monitor unused | `radar/smart_notifications.py` exists but workflow didn't call it | **Confirmed bug. Fixed wiring.** |
| Extra status reports | Workflow set `WEEKLY_REPORT: '1'`, while `SEND_FEED_ALERT` defaulted to `1` | **Prevented in workflow** (`0` for both, and heartbeat remains `0`) |
| Monitor state persisted | Prior workflow only committed database/encrypted state | **Fixed:** commits `data/monitor_state.json` |
| Scan cadence | GitHub `on: workflow_dispatch`; comment says cron-job.org dispatches every 15 min | **Left unchanged.** Actual external scheduler cannot be verified from ZIP. |
| Test suite | Local offline `python -m pytest -q` | **121 passed, 73 subtests passed** after adding 4 regression tests. |
| Stored history | `data/jobs.sqlite3` has 102 scan_runs, 1,908 opportunities, 3 notification_queue records | Historical snapshot only; counts will change after new scans |
| Three recurring eligible jobs | All three are BJAK / Ashby verified listings, all with queue state `sent` on 22 Oct 2026, 07:35 UTC | **0 new job alerts is expected** when those same three listings recur; `eligible` is per-scan, not newly eligible |
| Pixster Studio | No stored opportunity has Pixster as company or title | **Not discovered in saved history**, not a Telegram delivery failure |
| LinkedIn posts | `search/platform_discovery.py` targets `linkedin.com/jobs` through Google News RSS | Does **not directly monitor LinkedIn member hiring posts** |
| Manual career pages | `config/manual_career_pages.json` holds 5 reference URLs | Not scanned or alerted automatically |
| RSS verification | `allow_unverified_rss: false` in profile | Unverified Google News/LinkedIn leads cannot become alerts, by design |
| Source failure | `source_health` shows 17 historical `ReadTimeout` failures for `lever:Jobgether` | Intermittent source problem, not evidence the entire scan fails |
| Role preferences | Profile prefers UI/UX, UI, UX, product and interaction designer; excludes senior & unrelated design roles | Matches stated preferences. A post advertising both senior/junior roles still requires an actual discovered, individually verifiable vacancy. |

**Key limitation:** A green GitHub Actions run verifies execution, not completeness of job coverage. The notification fix only changes Telegram summary behavior; it does not introduce LinkedIn Posts API monitoring or guarantee discovery of the Pixster Studio post.
