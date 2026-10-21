# DIP JOB RADAR V2 — Matching-engine upgrade

This is a **targeted patch**, not a complete project or a replacement database.
It was built from the `DIP_JOB_RADAR-main.zip` supplied in the conversation.

## Included replacement files

Copy the following paths into the root of your existing `DIP_JOB_RADAR` Git repository, preserving their relative paths:

- `DIP_JOB_RADAR_FREE/radar/matching.py`
- `DIP_JOB_RADAR_FREE/radar/verification.py`
- `DIP_JOB_RADAR_FREE/search/ats.py`
- `DIP_JOB_RADAR_FREE/tests/test_matching_engine_upgrade.py` (new)

The patch does **not** replace your workflow YAML, watchlist JSON, candidate profile, Telegram settings, existing `radar/v2.py` diagnostics, or your SQLite history.

## What changes

1. **Role aliases:** UI/UX, UX/UI, UI UX, user-interface/user-experience, product, graphic/graphics, visual, interaction designer, and closely related phrases. Only roles listed in your profile are eligible; generic keyword matches no longer override explicit preferences.
2. **Location checks:** Ahmedabad and Gandhinagar remain accepted. India-only locations require separate, affirmative remote-work evidence (from a work-mode field or vacancy text). Generic global-remote postings without India eligibility remain excluded.
3. **Public ATS fields:** Ashby `isRemote` and Lever `workplaceType` are read when present, providing more reliable location signals.
4. **Explainable scores:** Verified ATS listings are scored without an Ahmedabad-only keyword requirement. Valid Gandhinagar or remote-India positions start above the configured score threshold of 65; optional role skills can increase the score.
5. **Existing safety filters:** Senior roles, unsuitable occupations, excessive required experience, training, search pages, and unverified RSS leads remain excluded by default.

## Install safely

1. Back up your current repository (or create a new branch).
2. Extract this ZIP locally. **Do not upload the ZIP file itself expecting GitHub to unzip it.**
3. Copy the four paths listed above into your repository, replacing the three existing files and adding the new test file.
4. From the repository root, run:

   ```bash
   cd DIP_JOB_RADAR_FREE
   python -m pip install -r requirements.txt pytest
   python -m pytest -q
   ```

5. Commit the file changes and push to GitHub. GitHub Actions will run the tests before scanning.
6. Expand the GitHub Actions **Scan / deliver** logs. Compare `[RUN]`, `[REJECTION BREAKDOWN]`, and `[LOCATION REVIEW]` results with your earlier run.

## Important constraints

- **Not a guarantee of new alerts.** Actual outcomes depend on employer jobs and the information returned by ATS APIs. The code cannot safely infer remote eligibility from `India` alone.
- No live public ATS calls or Telegram notifications were sent during this offline test.
- `RADAR_STATE_KEY` was empty in your earlier workflow screenshots. This patch does not configure that separate encryption secret.
- `radar/scoring.py` remains unchanged for backward compatibility with the V1 scanner; V2 scoring is implemented in `radar/matching.py`.
- GitHub Actions may run automatically after the new files are pushed. Consider temporarily disabling scheduled scans or using a test branch if you want to review alerts before enabling live delivery.

## Verification

Offline test suite: **88 passed**, including regression tests for location evidence and synthetic full-scanner eligibility.
