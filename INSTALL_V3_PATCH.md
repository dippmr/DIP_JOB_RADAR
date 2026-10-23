# DIP JOB RADAR V3 — installation (23 October 2026)

## What was changed

- Scheduled checks of the five previously configured employer career URLs plus a newly verified Pixster Studio official job-detail URL. Each page must really mention the watched title; a matching watchlist entry alone cannot produce a job.
- Individual public employer career detail pages can produce verified alerts only if the live content includes the role, application/hiring evidence, supported location, and an appropriate job-specific URL. Generic career indexes are **not verified** and go to review.
- A hiring post listing multiple roles is parsed into separate candidates (e.g. Senior and Junior Product Designer), with each role evaluated separately. Mixed Graphic and UI/UX advertisements retain only relevant UI/UX candidates.
- New `review_leads` SQLite table holds suitable **unverified** RSS, hiring-announcement and career-index tips. These tips are **never sent as verified immediate alerts**; up to five appear as clearly labelled unverified leads inside the **existing once-a-day 9 PM IST Telegram report**.
- Telegram users may manually submit **public** hiring-post text using `/lead https://post-url | Company name | Full hiring post text`. This does not fetch LinkedIn. The bot stores only selected public job metadata; do not send confidential or personal information. Role extraction and locality checks apply. A short acknowledgement is sent only for the user-triggered `/lead` request.
- Existing 15-minute external `workflow_dispatch`, immediate verified alerts, deduplication, silent scan runs, and 9 PM IST summary remain intact.
- Old SQLite tables and stored fingerprints remain intact, with additive schema only. Source-tracking records on career pages are now captured.

## Deployment — choose the *patch ZIP* (recommended)

1. Back up your GitHub repository/database first (download it or retain the last backup artifact).
2. Extract `DIP_JOB_RADAR_V3_PATCH_2026-10-23.zip` on your computer. **Do not upload the ZIP itself as a GitHub file.**
3. Copy the extracted files into the same paths **at the root** of `dippmr/DIP_JOB_RADAR`, keeping the exact directory hierarchy `.github/workflows/...` and `DIP_JOB_RADAR_FREE/...`. Commit all changes in **one commit**. Never replace `DIP_JOB_RADAR_FREE/data/jobs.sqlite3` or `private_state.enc` with an older copy.
4. Ensure your existing GitHub Actions secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are still configured. `RADAR_STATE_KEY` is optional for `/lead` but required for encrypted feedback actions when feedback is enabled. Never add these to source code.
5. Go to **Actions → DIP JOB RADAR V3 → Run workflow** once. The workflow runs tests before the live scanner. Check the **Scan / deliver** log for `[CAREER] checked=6 successful=... role_evidence=...` and `[RUN]`. **Do not infer live career verification unless the log shows career evidence and relevant alerts.**
6. Keep the already-configured **cron-job.org workflow-dispatch** schedule at 15 minutes. There is **no GitHub cron** to add and no need to modify cron-job.org if it still dispatches the current main workflow.
7. In Telegram, test a manual `/lead` with a public post URL, company and the full role/location text (example below). This will acknowledge saving an **unverified** review lead, not send an automatic verified job alert.
8. After 9 PM IST, check the daily report for review leads and review the linked source directly before applying.

## Telegram manual lead example

```
/lead https://www.example.com/public-post/123 | Example Studio | We're hiring a Junior Product Designer (UI/UX) in Ahmedabad. Apply now. Figma and wireframing required.
```

The URL above is deliberately an EXAMPLE and not a real vacancy. Replace with the public post's actual URL. Paste text (not screenshots). The bot does **not** use LinkedIn automation or scrape private feed content.

## Known gaps (not fixed in this patch)

- **Automatic coverage of regular LinkedIn posts is still incomplete**. Google News RSS may or may not index them; no authorized LinkedIn Posts API is configured. V3 does **not** claim to detect every recruiter post. The manual Telegram `/lead` feature is a user-initiated fallback, not automatic discovery.
- Career sites built fully with client-side JavaScript, CAPTCHAs, anti-bot restrictions, login requirements, or redirects may not return usable HTML. Failures are logged as source failures, not disguised as successful discovery.
- The six configured employer career URLs include five previously supplied pages and the official Pixster Studio Junior Product Designer page and are not a comprehensive Ahmedabad/Gandhinagar watchlist. More validated companies can be added to `config/manual_career_pages.json` after review.
- Some generic career pages may mention roles they hire for without an active opening. These are review-only leads, never verified alerts.
- The job alert email importer still needs independent IMAP credentials and is disabled by default. Existing email alert behavior is unchanged.
- The scanner may still be unable to verify a vacancy that appears solely inside a social post. Do not override verification simply to increase alert counts.

## Quality checks performed

- Offline Python test suite: `python -m pytest -q` — 140 tests passed plus 73 unittest subtests.
- Screenshot-based benchmark tests are **synthetic text extracted from the user-provided examples**; they do not demonstrate that the posts were fetched from LinkedIn.
- No successful live GitHub Actions run, public career-site HTTP fetch from the running project, or real Telegram message delivery was possible from the build environment. Verify deployment with GitHub logs.

## Operational behavior

| Event | Telegram behavior |
| --- | --- |
| Ordinary scan every 15 minutes | Silent |
| New verified matching employer job | Immediate, subject to queue/dedup and delivery |
| Unverified indexed post / generic career lead | Queued; up to five in 9 PM IST daily report |
| User enters `/lead ...` | One acknowledgement, and possible inclusion in the review queue |
| Daily summary after 9 PM IST | Once per day on first successful run |
| Repeated GitHub workflow failures | One alert when three consecutive failures are first reached |

