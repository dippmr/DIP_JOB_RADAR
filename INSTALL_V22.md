# DIP JOB RADAR V2.2 — safer job-platform discovery

## What this package REALLY adds

1. **Google News RSS site-restricted searches** for LinkedIn, Naukri, Indeed, Apna, Internshala, Wellfound, Cutshort and Behance. This is **indirect discovery from an RSS index**. It is **not a direct platform API**, does not browse/scrape job-board websites, and does not guarantee that Google News indexes their jobs.
2. **Optional read-only job-alert email import** via a separate IMAP mailbox/label. Its parser recognizes individual-job links on those eight websites. It never follows tracking redirects, uses IMAP `BODY.PEEK[]`, and does not mark messages read. Actual email layouts and tracking-link behavior differ by provider, so some job emails may not yield any usable individual-job link.
3. **Optional Telegram manual-review digest** for email leads that have a matching role and explicit Ahmedabad/Gandhinagar or remote India location. Every digest is conspicuously **UNVERIFIED**. It is separate from the verified ATS alert queue and from the `[RUN] eligible=` statistic.
4. **Offline tests** for supported domains, unsafe links, email dates, privacy, no-spam deduplication, and the scanner integration.

Existing ATS monitoring, `radar/matching.py` (your V2 matching patch), watchlist, Telegram secrets, SQLite history and feedback stay intact. Do **not** delete `DIP_JOB_RADAR_FREE/data/jobs.sqlite3`.

## Install to your public GitHub repository

1. Back up `main` or create an upgrade branch.
2. Extract this ZIP.
3. In your existing repository, **replace/add only the paths included in the ZIP**; do not upload a second nested `DIP_JOB_RADAR_FREE/` folder.
4. In particular, replace `.github/workflows/main.yml` with the included version so the new environment options exist. Keep your existing Telegram secrets.
5. Commit and push. Open Actions > DIP JOB RADAR V2 > Run workflow.
6. Expand `Test code` and `Scan / deliver` logs. Expected normal scan lines:

```
[DISCOVERY] indexed:LinkedIn: N RSS leads (unverified)
[RUN] sources=..., failures=..., unique=..., eligible=..., queued=..., sent=...
[REJECTION BREAKDOWN]
```

The platform queried in any one run rotates, so you will **not** see all eight websites every run. The 24 preset queries circulate across runs. Some index searches may return zero items; that is not proof of zero jobs.

## Optional: connect official job-alert emails

**Safer:** Create a **separate mailbox dedicated to job alerts**. The IMAP password/token grants broad access to the account even though this code uses read-only commands. Do not connect your primary personal inbox if it contains private correspondence. Never commit or screenshot passwords. Only configure email you own and are authorized to read.

1. On desired job platforms, create account-native job alerts for **Graphic Designer, UI/UX Designer, Visual Designer, Product Designer**, scoped to **Ahmedabad, Gandhinagar or India-eligible remote work**. Choose **email** delivery when available. LinkedIn and Indeed publicly document this option; verify whether the other six offer an equivalent feature on your account.
2. Forward those alert emails into your **dedicated account / IMAP folder** named `JobRadar`. The folder must exist before running the scanner (e.g., create a Gmail label called `JobRadar` and add Gmail filters to label incoming job alerts).
3. Add GitHub repository **Settings > Secrets and variables > Actions > New repository secret**:

   - `JOB_ALERT_IMAP_HOST` = `imap.gmail.com` (only if using Gmail; otherwise your provider's actual IMAP hostname)
   - `JOB_ALERT_IMAP_USER` = full mailbox address
   - `JOB_ALERT_IMAP_PASSWORD` = **separate app password** for the dedicated mailbox, if your provider supports it. Do **not** use your normal account password.

   Gmail supports IMAP and app passwords for some 2-Step Verification accounts, although Google recommends OAuth and app passwords may be unavailable on some account types. This implementation is **IMAP app-password based**, not Gmail OAuth; if your provider requires OAuth, leave the email feature disabled.
4. Edit `.github/workflows/main.yml` and change:

```
JOB_ALERT_EMAIL_ENABLED: '0'
```

   to:

```
JOB_ALERT_EMAIL_ENABLED: '1'
```

5. **Optional:** to receive **UNVERIFIED** matching email tips separately in Telegram, also change `SEND_EMAIL_LEAD_DIGEST: '0'` to `'1'`. Keep it off if you only want leads saved in the SQLite/dashboard for manual review.
6. Rerun and inspect:

```
[DISCOVERY] alert_emails: N unverified individual-job links
[LEADS] matching_email_tips=N, digest_items_sent=N (UNVERIFIED)
```

If `[WARN] alert_emails:` appears, check the account, secrets, folder, app-password permissions and access policy. **No secrets or entire email bodies are printed**.

## Boundaries

- **No direct scraping** of LinkedIn, Naukri, Indeed, Apna, Internshala, Wellfound, Cutshort or Behance is performed. A website supporting user-facing job alerts does not imply an open public jobs API.
- Tracking redirect links (e.g. third-party click trackers) are not followed. Such emails may produce zero leads until they include direct job-detail URLs. URL query tracking is removed before writing into your **public repository SQLite database**.
- The parser does **not** confirm employer identity, remote eligibility, that a listing is open, or that a page is scam-free. A city extracted from an email is explicitly *unverified email evidence*.
- Some job alerts arrive as complex digests or don't contain direct vacancy links; the conservative parser may miss them. This cannot be fixed safely by indiscriminate web scraping.
- No new external paid APIs or Python dependencies are required.
- Gmail app passwords are **not Google's preferred sign-in method**; use a separate account if you choose this approach. OAuth integration could be a future upgrade.
- Public `data/jobs.sqlite3` already stores job URLs and titles. Keep the dedicated mailbox free of personal/private content; the importer intentionally never stores full email bodies, sender addresses, recipient addresses or email headers. The sanitized job link and short extracted job title/location may still reveal which public vacancies you are watching.
- Automated verified-job alerts remain limited to published configured ATS boards, and any deliberately enabled V2 unverified RSS setting. Email tips **never automatically become verified**, even if `allow_unverified_rss` is turned on.

## Developer checks

From `DIP_JOB_RADAR_FREE/`:

```
python -m pip install -r requirements.txt pytest
python -m pytest -q
DRY_RUN=1 ATS_ENABLED=0 RSS_ENABLED=0 PLATFORM_RSS_ENABLED=0 JOB_ALERT_EMAIL_ENABLED=0 python -m radar.v2
```

The last command performs a no-network sanity check with an in-memory database and never sends Telegram messages.

## Documentation

- LinkedIn job alerts: https://www.linkedin.com/help/linkedin/answer/a511279/job-alerts-on-linkedin
- Indeed job alerts: https://www.indeed.com/help/job-seekers/articles/204488890-starting-stopping-and-managing-job-alerts?co=IN&hl=en
- LinkedIn automated scraping restriction: https://www.linkedin.com/help/linkedin/answer/a1341387/prohibition-of-scraping-software
- Gmail app passwords: https://support.google.com/mail/answer/185833
- Gmail IMAP: https://support.google.com/mail/answer/7126229
