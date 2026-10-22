# DIP JOB RADAR — UI/UX / Product Design Source Optimization

**Prepared:** 2026-10-22. **Tests:** 109 passed, 73 subtests passed (offline).

## Install in your existing GitHub repo

1. Download and unzip **DIP_JOB_RADAR_UIUX_SOURCE_PATCH.zip**.
2. Open your GitHub repository's main branch.
3. Copy **all paths exactly as shown** into the repository. Replace existing files where present:
   - `DIP_JOB_RADAR_FREE/config/company_watchlist.json`
   - `DIP_JOB_RADAR_FREE/config/manual_career_pages.json` (new, **manual reference only**)
   - `DIP_JOB_RADAR_FREE/radar/v2.py`
   - `DIP_JOB_RADAR_FREE/radar/verification.py`
   - `DIP_JOB_RADAR_FREE/tests/test_source_optimization.py` (new)
4. Commit all changes and open GitHub **Actions → DIP JOB RADAR V2 → Run workflow**.
5. Expand **Test code** and then **Scan / deliver**. Inspect lines starting `[SOURCE]`, `[RUN]`, and `[REJECTION BREAKDOWN]`.

**IMPORTANT:** Do not replace or delete `data/jobs.sqlite3`, existing Telegram secrets, other configuration files, or `.github/workflows/main.yml`. They are **not** included in this patch.

## Changes

- Added **BJAK** (Ashby token `bjakcareer`) and **Tempo Labs** (Ashby token `tempo`) to automatic employer-hosted ATS scanning. Public job page evidence:
  - https://jobs.ashbyhq.com/bjakcareer/5fec0d01-c1bf-47b3-880d-640d0fbbf216
  - https://jobs.ashbyhq.com/tempo/d37e806a-9e55-46fe-a681-09957a6d8e4c
- Kept PlayPower Labs, QuillBot, Drivetrain, Jobgether and HighLevel enabled.
- Disabled **Loopio, Valerie Group and e.l.f. Beauty** to cut geographic/role noise. Entries remain in JSON for future re-enabling.
- The ATS discovery stage now forwards only job titles in your **preferred-role groups** to the scanner (`ATS_TITLE_PREFILTER=1` by default). It does NOT override location, experience, seniority, verification, or freshness gates. Full board fingerprints remain available for existing closed-job detection.
- Logs distinguish all employer published listings from preferred-role candidates: `[SOURCE] ...: N published listings, M preferred-role candidates`.
- Improved India-remote location recognition when an employer explicitly writes **"This role is remote"** in the vacancy while the employer's location is India.
- The Telegram heartbeat now says **"candidates this run"** instead of incorrectly implying every record is newly discovered.
- Added 5 verified public **manual career links** relevant to Ahmedabad/Gandhinagar/India remote. They are reference links only; no HTML site scraping, no automatic matching and no Telegram alerts are generated for those pages. See `config/manual_career_pages.json`.

## Boundaries / what is not confirmed

- Public employer ATS *vacancy pages* were found on 2026-10-22, but direct Ashby API responses could not be reached from this offline environment; GitHub Actions will test the live endpoints. Current availability and role eligibility are not guaranteed.
- Google News RSS and indexed LinkedIn/Naukri/etc leads remain unverified; they are **not** direct LinkedIn/Naukri integrations and are not promoted to verified ATS alerts.
- Jobs may still be rejected due to 3+ years threshold interpretation, seniority, exact location, age (>21 days), and duplicates. **Zero eligible jobs is possible even with a correctly running scanner.**
- This package includes no secrets, Telegram credentials, private state or database changes.

## Test locally (optional)

From `DIP_JOB_RADAR_FREE/`:

```
python -m pytest -q
```

To disable the optional early ATS title prefilter for diagnostics, set the GitHub workflow env `ATS_TITLE_PREFILTER: 0` (this reintroduces irrelevant candidates but does not weaken final matching).
