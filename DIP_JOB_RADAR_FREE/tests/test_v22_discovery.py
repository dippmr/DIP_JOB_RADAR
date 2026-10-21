"""Offline regression tests for V2.2 discovery, safety and no-scraping boundaries."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from radar.database import RadarDB
from radar.lead_digest import reviewable_email_leads, send_lead_digest
from radar.v2 import collect, scan
from radar.verification import verify_job
from search.email_alerts import fetch_email_alerts, individual_job_url, parse_alert_message
from search.platform_discovery import PLATFORMS, platform_queries, rotate_platform_queries
from search.rss_search import SearchResult
from tests.test_matching_engine_upgrade import KEYWORDS, PROFILE


def make_email(links: list[tuple[str, str, str]], *, age_days: int = 0) -> bytes:
    msg = EmailMessage()
    msg["From"] = "Job alerts <updates@example.com>"
    msg["To"] = "personal@example.com"
    msg["Date"] = format_datetime(datetime.now(timezone.utc) - timedelta(days=age_days))
    msg["Subject"] = "Designer opportunities"
    msg.set_content("Your job alerts are ready")
    anchors = "".join(f'<p><a href="{url}">{title}</a><span>{context}</span></p>' for url, title, context in links)
    msg.add_alternative("<html><body>" + anchors + "</body></html>", subtype="html")
    return msg.as_bytes()


class PlatformDiscoveryTests(unittest.TestCase):
    def test_all_eight_search_sources(self):
        self.assertEqual(len(PLATFORMS), 8)
        self.assertEqual(len(platform_queries()), 24)
        text = " ".join(query for _, query in platform_queries())
        for domain in PLATFORMS.values():
            self.assertIn("site:" + domain, text)

    def test_time_based_rotation(self):
        queries = rotate_platform_queries(per_run=4, now=datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc))
        next_queries = rotate_platform_queries(per_run=4, now=datetime(2026, 10, 21, 10, 15, tzinfo=timezone.utc))
        self.assertEqual(len(queries), 4)
        self.assertFalse(set(queries) & set(next_queries))
        self.assertEqual(rotate_platform_queries(per_run=0), [])
        with self.assertRaises(ValueError):
            rotate_platform_queries(per_run=-1)


class EmailUrlTests(unittest.TestCase):
    def test_supported_job_detail_links(self):
        samples = [
            ("LinkedIn", "https://www.linkedin.com/jobs/view/12345678?trk=secret"),
            ("Naukri", "https://www.naukri.com/job-listings-ui-designer-company-12345?tracking=abc"),
            ("Indeed", "https://in.indeed.com/viewjob?jk=abcde12345&from=alert"),
            ("Apna", "https://apna.co/job/graphic-designer-12345"),
            ("Internshala", "https://internshala.com/internship/detail/graphic-design-999"),
            ("Wellfound", "https://wellfound.com/jobs/1234567"),
            ("Cutshort", "https://cutshort.io/job/UI-Designer-12345"),
            ("Behance", "https://www.behance.net/joblist/graphic-designer-12345"),
        ]
        for name, link in samples:
            with self.subTest(name=name):
                output = individual_job_url(link)
                self.assertIsNotNone(output)
                self.assertEqual(output[0], name)
                self.assertNotIn("tracking=", output[1])
                self.assertNotIn("trk=", output[1])
                self.assertNotIn("from=alert", output[1])
        self.assertEqual(individual_job_url(samples[2][1])[1], "https://in.indeed.com/viewjob?jk=abcde12345")

    def test_block_tracking_redirects_and_unsafe_urls(self):
        invalid = [
            "http://www.linkedin.com/jobs/view/12345",
            "https://linkedin.com.evil.example/jobs/view/12345",
            "https://evil.example/redirect?url=https://linkedin.com/jobs/view/12345",
            "https://linkedin.com/jobs/search/?keywords=design",
            "https://www.naukri.com/design-jobs-in-ahmedabad",
            "https://www.linkedin.com@evil.example/jobs/view/12345",
            "https://linkedin.com:8080/jobs/view/12345",
            "javascript:alert(1)",
            "https://indeed.com/viewjob?jk=abc&token=secret",
        ]
        for url in invalid:
            with self.subTest(url=url):
                self.assertIsNone(individual_job_url(url))


class EmailParserTests(unittest.TestCase):
    def test_extract_single_job_without_private_mail_text(self):
        raw = make_email([
            ("https://www.linkedin.com/jobs/view/12345678?trk=abc", "Graphic Designer", "Ahmedabad | User secret ID: 123456"),
            ("https://evil.example/unsubscribe", "Unsubscribe", ""),
        ])
        result = parse_alert_message(raw)
        self.assertEqual(len(result), 1)
        job = result[0]
        self.assertEqual(job.title, "Graphic Designer")
        self.assertEqual(job.location, "Ahmedabad")
        self.assertEqual(job.source_kind, "email")
        self.assertEqual(job.published, "")
        self.assertNotIn("secret", job.description)
        self.assertNotIn("trk=", job.url)
        self.assertNotIn("personal@example.com", str(job))

    def test_remote_india_and_foreign_location(self):
        raw = make_email([
            ("https://wellfound.com/jobs/2345678", "UI/UX Designer", "Fully remote, India"),
            ("https://cutshort.io/job/Product-Designer-1234", "Product Designer", "San Francisco"),
        ])
        output = parse_alert_message(raw)
        self.assertEqual(len(output), 2)
        self.assertEqual(output[0].location, "Remote - India")
        self.assertEqual(output[1].location, "")

    def test_no_audited_job_from_search_url_and_stale_email(self):
        raw = make_email([
            ("https://www.linkedin.com/jobs/search/?keywords=designer", "UI/UX Designer", "Ahmedabad"),
            ("https://www.linkedin.com/jobs/view/12345678", "Sales Executive", "Ahmedabad"),
        ])
        self.assertEqual(parse_alert_message(raw), [])
        self.assertEqual(parse_alert_message(make_email([(
            "https://www.linkedin.com/jobs/view/12345678", "Product Designer", "Ahmedabad")], age_days=15)), [])

    def test_private_plain_text_is_not_persisted(self):
        msg = EmailMessage()
        msg["Date"] = format_datetime(datetime.now(timezone.utc))
        msg["Subject"] = "Design job"
        msg.set_content("Graphic Designer — Ahmedabad\nhttps://www.linkedin.com/jobs/view/12345678?trk=personal")
        jobs = parse_alert_message(msg.as_bytes())
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].location, "Ahmedabad")


class ReadOnlyImapTests(unittest.TestCase):
    def test_imap_readonly_peek_and_folder_scoped(self):
        fixture = make_email([("https://www.linkedin.com/jobs/view/12345678", "Graphic Designer", "Ahmedabad")])
        calls = []
        class FakeBox:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                pass
            def login(self, *_):
                calls.append("login")
            def select(self, folder, readonly=False):
                calls.append(("select", folder, readonly))
                return "OK", [b"1"]
            def uid(self, cmd, *args):
                calls.append((cmd, args))
                if cmd == "SEARCH":
                    return "OK", [b"123"]
                return "OK", [(b"1 (BODY[])", fixture)]
        with patch.dict("os.environ", {
            "JOB_ALERT_IMAP_HOST": "imap.gmail.com", "JOB_ALERT_IMAP_USER": "test@example.com",
            "JOB_ALERT_IMAP_PASSWORD": "fake-app-password", "JOB_ALERT_IMAP_FOLDER": "JobRadar"
        }):
            output = fetch_email_alerts(imap_factory=lambda *_, **__: FakeBox())
        self.assertEqual(len(output), 1)
        self.assertIn(("select", "JobRadar", True), calls)
        self.assertTrue(any(call[0] == "FETCH" and call[1][-1] == "(BODY.PEEK[])" for call in calls if isinstance(call, tuple)))

    def test_imap_missing_secret_fails_no_network(self):
        with patch.dict("os.environ", {"JOB_ALERT_IMAP_HOST": "", "JOB_ALERT_IMAP_USER": "", "JOB_ALERT_IMAP_PASSWORD": ""}):
            with self.assertRaises(ValueError):
                fetch_email_alerts()


class SafeCandidateTests(unittest.TestCase):
    def lead(self, title="Graphic Designer", location="Ahmedabad", link="https://www.linkedin.com/jobs/view/12345678"):
        return SearchResult(title, link, "", company="", location=location,
                            source_kind="email", source="LinkedIn · email alert (unverified)")

    def test_email_never_enters_verified_pipeline_even_if_rss_opted_in(self):
        lead = self.lead()
        verdict = verify_job(lead, {**PROFILE, "allow_unverified_rss": True})
        self.assertFalse(verdict.accepted)
        self.assertEqual(verdict.reason, "Job-alert email lead not independently verified")
        with TemporaryDirectory() as temp:
            db = RadarDB(Path(temp) / "test.sqlite3")
            try:
                unique, eligible, queued, rejected = scan(db, PROFILE, KEYWORDS, [lead])
                self.assertEqual((unique, eligible, queued), (1, 0, 0))
                self.assertEqual(rejected[verdict.reason], 1)
            finally:
                db.close()

    def test_manual_digest_optin_and_idempotent(self):
        with TemporaryDirectory() as temp:
            db = RadarDB(Path(temp) / "test.sqlite3")
            try:
                leads = [self.lead(), self.lead(title="Senior Graphic Designer", link="https://www.linkedin.com/jobs/view/99999111"),
                         self.lead(location="United States", link="https://www.linkedin.com/jobs/view/11111222")]
                self.assertEqual(len(reviewable_email_leads(leads, PROFILE)), 1)
                with patch("radar.lead_digest.send_message") as send:
                    count, sent = send_lead_digest(db, "token", "chat", leads, PROFILE)
                    self.assertEqual((count, sent), (1, 1))
                    self.assertIn("UNVERIFIED", send.call_args.args[2])
                    self.assertEqual(send_lead_digest(db, "token", "chat", leads, PROFILE), (1, 0))
                    self.assertEqual(send.call_count, 1)
            finally:
                db.close()

    def test_failed_send_does_not_mark_lead_sent(self):
        with TemporaryDirectory() as temp:
            db = RadarDB(Path(temp) / "test.sqlite3")
            try:
                with patch("radar.lead_digest.send_message", side_effect=RuntimeError("offline")):
                    with self.assertRaises(RuntimeError):
                        send_lead_digest(db, "token", "chat", [self.lead()], PROFILE)
                with patch("radar.lead_digest.send_message") as success:
                    _, sent = send_lead_digest(db, "token", "chat", [self.lead()], PROFILE)
                    self.assertEqual(sent, 1)
                    self.assertEqual(success.call_count, 1)
            finally:
                db.close()

    def test_collect_optional_sources_mocked(self):
        with TemporaryDirectory() as temp:
            db = RadarDB(Path(temp) / "test.sqlite3")
            try:
                with patch.dict("os.environ", {
                    "PLATFORM_RSS_ENABLED": "1", "PLATFORM_RSS_QUERIES_PER_RUN": "2",
                    "JOB_ALERT_EMAIL_ENABLED": "1",
                }), patch("radar.v2.GoogleNewsRSS") as rss, patch("radar.v2.fetch_email_alerts", return_value=[self.lead()]):
                    rss.return_value.search.return_value = []
                    found, total, fails, boards = collect(db, [], rss_enabled=False, dry=True)
                    self.assertEqual((len(found), total, fails), (1, 3, 0))
                    self.assertEqual(boards, [])
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
