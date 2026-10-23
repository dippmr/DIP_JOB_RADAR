# V3 engineering notes — prioritized by failure mode

## Discovery != verification != notification

The green Actions status only proves the pipeline completed. It does not mean a particular LinkedIn post was indexed or discovered. `radar.v2.collect` now probes six configured public career pages, including the official Pixster Studio Junior Product Designer job URL, while existing Google News RSS and ATS discovery remain. `search.post_parser` can split multi-vacancy text once the text is available. User-initiated `/lead` supplies otherwise inaccessible post text.

## Explicit role-level benchmark expectations

| Screenshot example | Parser result from supplied text | Final status |
| --- | --- | --- |
| Pixster Studio | Junior Product Designer and Senior Product Designer | Junior unverified review; senior excluded |
| Applen Solutions | UI/UX Designer, Ahmedabad | Unverified review |
| TechOwl | UI/UX Designer; Graphic Designer dropped | Unverified review |
| 1–3 month proof-of-concept project | UI/UX Designer, Ahmedabad | Unverified review (short contract, not an assumed full-time job) |

**None of these tests fetches LinkedIn.** They isolate extraction/matching from source coverage.

## Data and reliability safeguards

- `jobs` and `opportunities` tables are kept; `review_leads` is additive.
- Normal ATS/RSS fingerprints are unchanged. Post or generic-career-index leads include title in fingerprints to preserve separate roles on the same URL.
- Public career pages may return a verified `source_kind='career'` only on strict checks; index-only entries are `source_kind='career_lead'`.
- `review_leads` excludes rejected senior roles, wrong locations, and graphic-only roles. Delivery is not automatic.
- Telegram's `/lead` stores only extracted role/company/location/URL/reason in SQLite, *not entire Telegram message text*; only the configured chat is accepted.
- RSS or post items cannot be made verified by `allow_unverified_rss` when they were expanded as unverified posts.
- Daily review links are included in the existing daily report, **not** a second noisy notification every 15 minutes. Items are marked included only after Telegram reports successful delivery.
- Career URLs must be direct HTTPS public hostnames. Redirects and non-HTML responses are skipped rather than automatically followed. A domain with complex JS can require a separate permitted provider adapter.

## Next phase (not claimed complete)

1. Add more Ahmedabad/Gandhinagar businesses with independently confirmed public careers URLs, check robots/terms before enabling.
2. Enable opt-in job-alert email ingestion with the user's own account credentials, kept in GitHub Actions secrets.
3. Compare a weekly manually maintained sample of live vacancies against discovered URLs; measure recall and detection delay.
4. Use the source-health and review queue to tune the discovery mix; only then consider further API integrations.
