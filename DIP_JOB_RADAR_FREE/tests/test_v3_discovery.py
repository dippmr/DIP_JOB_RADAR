"""Offline V3 regression tests: benchmark examples are screenshots, not live fetches."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from radar.database import RadarDB, job_fp
from radar.review import review_reason
from radar.smart_notifications import IST, daily_statistics, process
from radar.v2 import scan
from radar.verification import role_groups, verify_job
from search.career_pages import VisibleText, download_page, page_candidate, secure_public_url
from search.post_parser import extract_hiring_leads, expand_rss_hiring_announcements
from search.rss_search import SearchResult
from tests.helpers import real_keywords

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / "config/profile.json").read_text())
ALLOWED = {"uiux", "ui", "ux", "product", "interaction"}


class PostExtractionTests(unittest.TestCase):
    def test_pixster_junior_and_senior_are_independent(self):
        content = ("We're Hiring at PIXSTER STUDIO! Open Positions:\n"
                   "Senior Product Designer (UI/UX)\n"
                   "Junior Product Designer (UI/UX)\n"
                   "Location: Ahmedabad (On-site) Employment: Full-time")
        leads = extract_hiring_leads(content, url="https://example.org/post/1",
                                     source="User-submitted announcement", company="Pixster Studio", allowed=ALLOWED)
        self.assertEqual(len(leads), 2)
        self.assertIn("Senior Product Designer", leads[0].title)
        self.assertIn("Junior Product Designer", leads[1].title)
        self.assertNotEqual(job_fp(leads[0]), job_fp(leads[1]))
        self.assertIn("seniority", verify_job(leads[0], PROFILE).reason)
        self.assertEqual(review_reason(leads[1], PROFILE), "Hiring post not independently verified")

    def test_applen_is_relevant_but_not_verified(self):
        text = ("We're Hiring | UI/UX Designer in Ahmedabad. "
                "Figma, Auto Layout, prototyping and developer handoff. "
                "1-2 years of relevant experience.")
        leads = extract_hiring_leads(text, url="https://example.org/post/applen", source="post",
                                     company="Applen Solutions", allowed=ALLOWED)
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0].location, "Ahmedabad")
        self.assertTrue(review_reason(leads[0], PROFILE))
        self.assertFalse(verify_job(leads[0], PROFILE).accepted)

    def test_graphic_plus_uiux_keeps_only_uiux_and_experience_limit(self):
        text = "We’re Hiring | Graphic Designer & UI/UX Designer. 3+ Years Experience. Ahmedabad."
        leads = extract_hiring_leads(text, url="https://example.org/post/techowl",
                                     source="post", allowed=ALLOWED)
        self.assertEqual([x.title for x in leads], ["UI/UX Designer"])
        self.assertTrue(review_reason(leads[0], PROFILE))

    def test_poc_short_term_role_is_lead_not_full_time(self):
        text = "Hiring: UI/UX Designer | Ahmedabad. 1–3 months proof of concept project."
        leads = extract_hiring_leads(text, url="https://example.org/post/poc", source="post", allowed=ALLOWED)
        self.assertEqual(len(leads), 1)
        self.assertEqual(review_reason(leads[0], PROFILE), "Hiring post not independently verified")
        self.assertFalse(verify_job(leads[0], PROFILE).accepted)

    def test_not_every_mention_is_hiring(self):
        content = "Top UI/UX Designer skills to learn this year! Here are 10 Figma tips."
        self.assertEqual(extract_hiring_leads(content, url="https://example.org/article", source="post"), [])

    def test_rss_multi_role_post_split(self):
        job = SearchResult("We're Hiring at EXAMPLE!", "https://news.google.com/articles/abc",
                           "Open Positions: Senior Product Designer, Junior Product Designer in Ahmedabad",
                           source="News", source_kind="rss")
        roles = expand_rss_hiring_announcements([job], ALLOWED)
        self.assertEqual(len(roles), 2)
        self.assertTrue(all(x.source_kind == "post" for x in roles))

    def test_post_not_automatically_promoted_with_rss_opt_in(self):
        post = extract_hiring_leads("Hiring UI/UX Designer Ahmedabad", url="https://example.org/1",
                                    source="post", allowed=ALLOWED)[0]
        self.assertFalse(verify_job(post, {**PROFILE, "allow_unverified_rss": True}).accepted)

    def test_role_detection_does_not_infer_unstated_junior(self):
        titles = extract_hiring_leads("We are hiring Senior and Junior Product Designer Ahmedabad",
                                      url="https://example.org/1", source="post", allowed=ALLOWED)
        self.assertEqual([x.title for x in titles], ["Junior Product Designer"])
        # This is only a text-extraction test, not a claim about job truth.


class CareerPageTests(unittest.TestCase):
    def test_specific_page_is_verified_only_with_live_page_evidence(self):
        page = {"company": "Tizora", "title": "UI/UX Designer", "url": "https://www.tizora.ai/careers/ui-ux-designer",
                "location": "Ahmedabad"}
        html = "<html><h1>UI/UX Designer</h1><p>We're hiring 2–3 years experience in Ahmedabad, India.</p><p>Apply now via email.</p></html>"
        reader = VisibleText(); reader.feed(html)
        result = page_candidate(page, reader.text())
        self.assertIsNotNone(result)
        self.assertEqual(result.source_kind, "career")
        self.assertEqual(result.location, "Ahmedabad")
        self.assertTrue(verify_job(result, PROFILE).accepted)
        self.assertEqual(verify_job(result, PROFILE).confidence, "employer")

    def test_pixster_official_junior_job_detail_url(self):
        page = {"company": "Pixster Studio", "title": "Junior Product Designer",
                "url": "https://www.pixsterstudio.com/jobs-opening/jr-product-designer"}
        content = ("Product Designer (0-1 years). 02 Openings. On Site. Ahmedabad. "
                   "We're looking for a Junior Product Designer who builds digital products. "
                   "1+ years of experience in Product Design. Apply Now.")
        job = page_candidate(page, content)
        self.assertEqual(job.source_kind, "career")
        self.assertTrue(verify_job(job, PROFILE).accepted)
        self.assertTrue(job.apply_url.endswith("jr-product-designer"))

    def test_generic_index_never_verified(self):
        page = {"company": "Tcules", "title": "UX/UI Designer (Generalist)", "url": "https://tcules.com/careers"}
        text = "Roles we hire across UX/UI Designer (Generalist). In office. Ahmedabad. Apply now."
        lead = page_candidate(page, text)
        self.assertIsNotNone(lead)
        self.assertEqual(lead.source_kind, "career_lead")
        self.assertFalse(verify_job(lead, PROFILE).accepted)

    def test_missing_job_or_city_cannot_use_watchlist_as_evidence(self):
        page = {"company": "Demo", "title": "UI/UX Designer", "location": "Ahmedabad",
                "url": "https://example.com/careers/ui-ux-designer"}
        self.assertIsNone(page_candidate(page, "We are hiring a Backend Engineer in Ahmedabad"))
        lead = page_candidate(page, "We are hiring UI/UX Designer. Apply now")
        self.assertIsNotNone(lead)
        self.assertEqual(lead.source_kind, "career_lead")
        self.assertEqual(lead.location, "")

    def test_no_private_hosts_unsupported_schemes_or_redirect(self):
        for url in ("http://example.com/careers", "https://localhost/careers",
                    "https://127.0.0.1/", "https://example.com@localhost/careers",
                    "https://example.com:8443/careers", "https://example.com.evil.local/"):
            self.assertFalse(secure_public_url(url), url)

    def test_download_does_not_follow_redirect(self):
        class FakeResponse:
            is_redirect = True
            headers = {"Content-Type": "text/html"}
            def raise_for_status(self): pass
            def close(self): pass
        class FakeSession:
            def get(self, url, **kwargs):
                self.kwargs = kwargs
                return FakeResponse()
        fake = FakeSession()
        with self.assertRaises(ValueError):
            download_page("https://example.com/careers", session=fake)
        self.assertFalse(fake.kwargs['allow_redirects'])


class QueueTests(unittest.TestCase):
    def test_unverified_post_goes_to_review_not_telegram(self):
        post = extract_hiring_leads("We are hiring Junior Product Designer in Ahmedabad",
                                    url="https://example.org/posts/abc", company="Demo",
                                    source="public", allowed=ALLOWED)[0]
        db = RadarDB(":memory:")
        try:
            unique, eligible, queued, rejected = scan(db, PROFILE, real_keywords(), [post])
            self.assertEqual((unique, eligible, queued), (1, 0, 0))
            self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM review_leads").fetchone()[0], 1)
            scan(db, PROFILE, real_keywords(), [post])
            self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM review_leads").fetchone()[0], 1)
            self.assertEqual(db.pending_alerts(), [])
        finally:
            db.close()

    def test_senior_and_unrelated_roles_do_not_enter_review(self):
        posts = extract_hiring_leads("Hiring Senior Product Designer and Graphic Designer in Ahmedabad",
                                     url="https://example.org/posts/def", source="public", company="Demo", allowed=ALLOWED)
        db = RadarDB(":memory:")
        try:
            scan(db, PROFILE, real_keywords(), posts)
            self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM review_leads").fetchone()[0], 0)
        finally:
            db.close()

    def test_daily_summary_includes_review_leads_only_once(self):
        db = RadarDB(":memory:")
        try:
            post = extract_hiring_leads("Hiring UI/UX Designer in Ahmedabad",
                                        url="https://example.org/post/1", source="public", company="Demo")[0]
            db.record_review_lead(post, "Hiring post not independently verified")
            with tempfile.TemporaryDirectory() as td:
                path = Path(td) / 'db.sqlite3'
                disk = RadarDB(path)
                disk.record_review_lead(post, "Hiring post not independently verified")
                disk.close()
                stats = daily_statistics(path, datetime.now(IST).date())
                self.assertEqual(len(stats['review_leads']), 1)
                sent = []
                from radar.smart_notifications import initial_state
                state, outcomes = process(initial_state(), success=True,
                                          now=datetime.now(IST).replace(hour=21),
                                          run_identifier='1:1', stats=stats,
                                          send=lambda text: sent.append(text) or True,
                                          run_link="https://github.com/test/actions")
                self.assertEqual(outcomes, ['daily summary'])
                self.assertIn('UNVERIFIED', sent[0])
                self.assertIn('https://example.org/post/1', sent[0])
                _, again = process(state, success=True, now=datetime.now(IST).replace(hour=21, minute=15),
                                   run_identifier='2:1', stats=stats, send=lambda t: True)
                self.assertEqual(again, [])
        finally:
            db.close()

if __name__ == '__main__':
    unittest.main()

class TelegramSubmissionTests(unittest.TestCase):
    def test_manual_lead_from_configured_chat_only_and_no_raw_post_storage(self):
        from radar.telegram_v2 import _ingest_lead_command, receive_feedback
        from radar.private_state import PrivateState

        class FakeResponse:
            def raise_for_status(self): pass
            def json(self):
                return {"ok": True, "result": [{"update_id": 20,
                        "message": {"chat": {"id": 123}, "text":
                            "/lead https://www.linkedin.com/posts/example-123?tracking=hi | Applen Solutions | "
                            "We're Hiring UI/UX Designer in Ahmedabad. Figma required."}},
                       {"update_id": 21,
                        "message": {"chat": {"id": 999}, "text":
                            "/lead https://example.org/other | Sneaky | Hiring UI/UX Designer in Ahmedabad"}}]}

        class FakeClient:
            def get(self, *args, **kwargs): return FakeResponse()
            def post(self, *args, **kwargs):
                class Sent:
                    def raise_for_status(self): pass
                    def json(self): return {"ok": True, "result": True}
                return Sent()
        with tempfile.TemporaryDirectory() as td:
            db = RadarDB(Path(td) / "db.sqlite3")
            try:
                state = PrivateState(Path(td) / "never.enc", key="")
                processed = receive_feedback("token", "123", db, state, session=FakeClient())
                self.assertEqual(processed, 1)
                row = db.conn.execute("SELECT title,company,url FROM review_leads").fetchone()
                self.assertEqual(row[0], "UI/UX Designer")
                self.assertEqual(row[1], "Applen Solutions")
                self.assertNotIn("tracking", row[2])
                self.assertNotIn("Figma required", str(db.conn.execute("SELECT * FROM review_leads").fetchone()))
                self.assertEqual(db.get_meta("telegram_update_offset"), "22")
            finally:
                db.close()

    def test_manual_lead_requires_link_company_post_text(self):
        from radar.telegram_v2 import _ingest_lead_command
        db = RadarDB(":memory:")
        try:
            message = _ingest_lead_command("/lead https://example.com/x | Example | hi", db)
            self.assertIn("not saved", message.lower())
            self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM review_leads").fetchone()[0], 0)
        finally:
            db.close()
