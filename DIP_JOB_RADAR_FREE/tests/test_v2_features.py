"""Offline V2 tests — no external HTTP calls, no Telegram credentials."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from cryptography.fernet import Fernet

from radar.assistant import build_application_prep
from radar.database import RadarDB, job_fp, cluster_key
from radar.matching import evaluate
from radar.private_state import PrivateState
from radar.telegram_v2 import format_alert, receive_feedback, send_alert
from radar.v2 import scan
from radar.verification import evaluate_location, required_years, verify_job
from search.ats import board_url, parse_ashby, parse_greenhouse, parse_lever, safe_link
from search.rss_search import SearchResult
from tests.helpers import real_keywords


PROFILE = {
    "preferred_roles": ["ui/ux designer", "product designer", "interaction designer"],
    "skills": ["figma", "prototyping"],
    "locations": ["ahmedabad"],
    "allow_remote_india": True, "allow_hybrid": False,
    "max_required_years": 3, "exclude_senior_roles": True,
    "excluded_companies": [], "score_threshold": 65,
    "allow_unverified_rss": False, "max_post_age_days": 21,
}


def ats(title="UI/UX Designer", company="Demo", location="Ahmedabad", desc="Figma prototyping", id="1"):
    return SearchResult(
        title, "https://jobs.example.com/" + id, desc, "", "Greenhouse · " + company,
        company=company, location=location, apply_url="https://jobs.example.com/apply/" + id,
        source_kind="ats", external_id="greenhouse:demo:" + id,
    )


class TestSources(unittest.TestCase):
    def test_greenhouse_parser_and_updated_not_published(self):
        listings = list(parse_greenhouse({"jobs": [
            {"id": 22, "title": "UI/UX Designer", "absolute_url": "https://example.com/job/22", "updated_at": "2026-10-21T12:00:00Z", "content": "<p>Figma</p>", "location": {"name": "Ahmedabad"}}
        ]}, "Foo", "foo"))
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].location, "Ahmedabad")
        self.assertEqual(listings[0].published, "")
        self.assertEqual(listings[0].description, "Figma")

    def test_lever_parser(self):
        job = list(parse_lever([{"id": "xyz", "text": "Product Designer", "hostedUrl": "https://jobs.lever.co/foo/xyz", "applyUrl": "https://jobs.lever.co/foo/xyz/apply", "descriptionPlain": "Figma", "categories": {"location": "Ahmedabad"}}], "Foo", "foo"))[0]
        self.assertEqual(job.company, "Foo")
        self.assertIn("Ahmedabad", job.location)

    def test_ashby_unlisted_is_not_alerted(self):
        docs = {"jobs": [{"id": "1", "title": "UI Designer", "jobUrl": "https://jobs.ashbyhq.com/test/1", "location": "Ahmedabad", "isListed": False}, {"id": "2", "title": "Product Designer", "jobUrl": "https://jobs.ashbyhq.com/test/2", "applyUrl": "https://jobs.ashbyhq.com/test/2/apply", "location": "Ahmedabad", "isListed": True}]}
        self.assertEqual(len(list(parse_ashby(docs, "Foo", "foo"))), 1)

    def test_token_validation_and_safe_links(self):
        with self.assertRaises(ValueError):
            board_url("invalid", "foo")
        with self.assertRaises(ValueError):
            board_url("greenhouse", "../bad")
        self.assertEqual(safe_link("javascript:alert(1)"), "")
        self.assertIn("api.lever.co", board_url("lever", "mycompany"))
        self.assertIn("api.ashbyhq.com", board_url("ashby", "mycompany"))


class TestVerification(unittest.TestCase):
    def test_real_vacancy(self):
        match = evaluate(ats(), PROFILE, real_keywords())
        self.assertTrue(match.accepted)
        self.assertGreaterEqual(match.score, 65)
        self.assertEqual(match.verification, "ats")

    def test_course_is_hard_rejected(self):
        self.assertFalse(verify_job(ats("UI/UX Designer Training Course"), PROFILE).accepted)

    def test_senior_is_hard_rejected(self):
        self.assertIn("seniority", verify_job(ats("Senior Product Designer"), PROFILE).reason)

    def test_company_history_is_not_an_experience_requirement(self):
        self.assertIsNone(required_years("A company with 20 years in the industry"))
        self.assertTrue(verify_job(ats(desc="A company with 20 years in the industry"), PROFILE).accepted)

    def test_excessive_experience_rejected(self):
        self.assertFalse(verify_job(ats(desc="Requires 5-8 years of experience with Figma"), PROFILE).accepted)
        self.assertEqual(required_years("Requires 5–8 years"), 5)

    def test_no_apply_url_is_not_trusted_ats(self):
        job = ats()
        job.apply_url = ""
        self.assertFalse(verify_job(job, PROFILE).accepted)

    def test_wrong_city(self):
        match = evaluate(ats(location="Mumbai"), PROFILE, real_keywords())
        self.assertFalse(match.accepted)

    def test_location_only_search_query_is_insufficient(self):
        job = SearchResult("UI/UX Designer Hiring", "https://example.com/vacancy/1", "We are hiring", "", "News", '"Ahmedabad"')
        self.assertFalse(evaluate_location(job, PROFILE)[0])

    def test_remote_india(self):
        self.assertTrue(evaluate_location(ats(location="Remote - India"), PROFILE)[0])
        self.assertFalse(evaluate_location(ats(location="Remote - US"), PROFILE)[0])

    def test_hybrid_exclusion(self):
        self.assertFalse(evaluate_location(ats(location="Ahmedabad (Hybrid)"), PROFILE)[0])

    def test_rss_is_unverified_without_opt_in(self):
        job = SearchResult("UI/UX Designer hiring in Ahmedabad", "https://example.com/job/1", "We are hiring", "", "News")
        self.assertFalse(verify_job(job, PROFILE).accepted)
        profile = {**PROFILE, "allow_unverified_rss": True}
        self.assertTrue(verify_job(job, profile).accepted)

    def test_excluded_company(self):
        profile = {**PROFILE, "excluded_companies": ["Demo"]}
        self.assertFalse(verify_job(ats(), profile).accepted)

    def test_result_pages(self):
        job = ats()
        job.url = "https://example.com/jobs/search?query=ui"
        self.assertFalse(verify_job(job, PROFILE).accepted)


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = RadarDB(Path(self.folder.name) / "jobs.sqlite3")

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def test_alert_queue_and_heuristic_dedup(self):
        a = ats(id="11")
        b = ats(id="12")
        self.assertNotEqual(job_fp(a), job_fp(b))
        self.assertEqual(cluster_key(a), cluster_key(b))
        fp = self.db.record_opportunity(a, 85, "ats", "", ["Good fit"])
        self.assertFalse(self.db.cluster_alerted(a))
        self.db.queue_alert(fp)
        self.assertTrue(self.db.cluster_alerted(b))
        self.assertEqual(self.db.pending_alerts()[0]["fingerprint"], fp)
        self.db.mark_alert_sent(fp)
        self.assertEqual(self.db.pending_alerts(), [])
        self.assertEqual(self.db.stats()["alerts_sent"], 1)

    def test_closed_job_detection_only_after_success(self):
        a = ats(id="13")
        fp = self.db.record_opportunity(a, 80, "ats", "", [])
        self.db.mark_closed_board_jobs(a.source, [])
        self.assertEqual(self.db.list_opportunities()[0]["last_status"], "not_seen_on_board")
        self.db.record_opportunity(a, 85, "ats", "", [])
        self.assertEqual(self.db.list_opportunities()[0]["last_status"], "active")

    def test_failed_notification_retries(self):
        job = ats(id="14")
        fp = self.db.record_opportunity(job, 88, "ats", "", [])
        self.db.queue_alert(fp)
        self.db.mark_alert_failed(fp, RuntimeError("secret token here"))
        row = self.db.conn.execute("SELECT attempts, last_error FROM notification_queue WHERE fingerprint=?", (fp,)).fetchone()
        self.assertEqual(row[0], 1)
        self.assertNotIn("secret", row[1])

    def test_scan_good_and_bad_records(self):
        good = ats(id="15")
        bad = ats(title="Senior UI/UX Designer", id="16")
        count, eligible, queued, reasons = scan(self.db, PROFILE, real_keywords(), [good, bad], dry=False)
        self.assertEqual((count, eligible, queued), (2, 1, 1))
        self.assertEqual(len(self.db.list_opportunities()), 2)
        self.assertEqual(len(self.db.pending_alerts()), 1)

    def test_old_legacy_state_survives(self):
        self.db.add("old-fp", SimpleNamespace(title="old", url="https://x", source="X", description=""), 50, True)
        self.assertTrue(self.db.seen("old-fp"))
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 1)


class TestFeedback(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.key = Fernet.generate_key().decode()
        self.path = Path(self.folder.name) / "private_state.enc"

    def tearDown(self):
        self.folder.cleanup()

    def test_encrypt_roundtrip_and_never_plaintext(self):
        state = PrivateState(self.path, self.key)
        state.set_feedback("abc123", "saved")
        self.assertNotIn(b"saved", self.path.read_bytes())
        self.assertEqual(PrivateState(self.path, self.key).get_feedback("abc123"), "saved")

    def test_invalid_key_does_not_destroy_state(self):
        state = PrivateState(self.path, self.key)
        state.set_feedback("abc", "applied")
        original = self.path.read_bytes()
        with self.assertRaises(RuntimeError):
            PrivateState(self.path, Fernet.generate_key().decode())
        self.assertEqual(original, self.path.read_bytes())

    def test_unknown_status_fails(self):
        with self.assertRaises(ValueError):
            PrivateState(self.path, self.key).set_feedback("abc", "spam")


class FakeTelegramSession:
    def __init__(self, updates):
        self.updates = updates
        self.posted = []
    def get(self, url, params=None, timeout=None):
        return FakeHTTPResponse({"ok": True, "result": self.updates})
    def post(self, url, json=None, timeout=None):
        self.posted.append((url, json))
        return FakeHTTPResponse({"ok": True, "result": {}})


class FakeHTTPResponse:
    def __init__(self, data):
        self.data = data
    def raise_for_status(self):
        return None
    def json(self):
        return self.data


class TestTelegram(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = RadarDB(Path(self.folder.name) / "jobs.sqlite3")
        self.state = PrivateState(Path(self.folder.name) / "private.enc", Fernet.generate_key().decode())
        job = ats(id="17")
        self.fp = self.db.record_opportunity(job, 90, "ats", "", ["Location verified"])

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def test_callback_authorization(self):
        updates = [
            {"update_id": 21, "callback_query": {"id": "bad", "data": "saved:" + self.fp[:20], "message": {"chat": {"id": "other"}}}},
            {"update_id": 22, "callback_query": {"id": "good", "data": "saved:" + self.fp[:20], "message": {"chat": {"id": "mine"}}}},
        ]
        self.assertEqual(receive_feedback("token", "mine", self.db, self.state, FakeTelegramSession(updates)), 1)
        self.assertEqual(self.state.get_feedback(self.fp), "saved")
        self.assertEqual(self.state.data["offset"], 23)

    def test_alert_markup_and_html_escaping(self):
        row = self.db.list_opportunities()[0]
        row["fingerprint"] = self.fp
        message = format_alert({**row, "title": "UI/UX <Designer>"})
        self.assertIn("&lt;Designer&gt;", message)
        client = FakeTelegramSession([])
        send_alert("token", "mine", row, with_feedback=True, session=client)
        keyboard = client.posted[-1][1]["reply_markup"]["inline_keyboard"]
        self.assertEqual(len(keyboard), 4)
        self.assertIn(self.fp[:20], keyboard[0][0]["callback_data"])


class TestAssistant(unittest.TestCase):
    def test_app_prep_never_claims_user_experience(self):
        result = build_application_prep({"title": "UI/UX Designer", "company": "Demo", "url": "https://example.com", "apply_url": "https://example.com/apply", "description": "Figma role"}, PROFILE)
        self.assertIn("Figma".lower(), result.lower())
        self.assertIn("[real project", result)
        self.assertIn("Do not invent experiences", result)


if __name__ == "__main__":
    unittest.main()
