"""Offline tests for the 15-minute smart notification policy."""
import sqlite3
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from radar.database import RadarDB
from radar.smart_notifications import IST, daily_statistics, initial_state, process, write_state, load_state


class TestSmartNotifications(unittest.TestCase):
    def setUp(self):
        self.state = initial_state()
        self.messages = []
        self.now = datetime(2026, 10, 22, 20, 0, tzinfo=IST)

    def send(self, txt):
        self.messages.append(txt)
        return True

    def execute(self, success, n, now=None, stats=None, send=None):
        self.state, sent = process(
            self.state, success=success, now=now or self.now,
            run_identifier=f"job:{n}", send=send or self.send,
            stats=stats, run_link="https://github.com/test/repo/actions/runs/123",
        )
        return sent

    def test_silent_successes_and_reset(self):
        self.assertEqual(self.execute(True, 1), [])
        self.assertEqual(self.messages, [])
        self.execute(False, 2)
        self.execute(False, 3)
        self.assertEqual(self.execute(True, 4), [])
        self.assertEqual(self.state["consecutive_failures"], 0)
        self.assertEqual(self.execute(False, 5), [])
        self.assertEqual(self.messages, [])

    def test_warning_only_on_third_failure_and_new_streak(self):
        self.execute(False, 1)
        self.execute(False, 2)
        self.assertEqual(self.messages, [])
        self.assertEqual(self.execute(False, 3), ["three-failure warning"])
        self.execute(False, 4)
        self.assertEqual(len(self.messages), 1)
        self.execute(True, 5)
        self.execute(False, 6)
        self.execute(False, 7)
        self.execute(False, 8)
        self.assertEqual(len(self.messages), 2)

    def test_retry_warning_if_delivery_fails(self):
        self.execute(False, 1)
        self.execute(False, 2)
        self.execute(False, 3, send=lambda _: False)
        self.assertFalse(self.state["failure_warning_sent"])
        self.execute(False, 4)
        self.assertTrue(self.state["failure_warning_sent"])
        self.assertEqual(len(self.messages), 1)

    def test_only_one_report_after_nine_pm(self):
        stats = dict(completed=81, reviewed=1264, source_failures=2,
                     newly_eligible=3, alerts_sent=2)
        self.execute(True, 1, now=datetime(2026, 10, 22, 20, 59, tzinfo=IST), stats=stats)
        self.assertEqual(len(self.messages), 0)
        self.execute(True, 2, now=datetime(2026, 10, 22, 21, 15, tzinfo=IST), stats=stats)
        self.assertEqual(len(self.messages), 1)
        self.assertIn('New eligible jobs discovered: 3', self.messages[0])
        self.execute(True, 3, now=datetime(2026, 10, 22, 21, 30, tzinfo=IST), stats=stats)
        self.assertEqual(len(self.messages), 1)
        self.execute(True, 4, now=datetime(2026, 10, 23, 21, 15, tzinfo=IST), stats=stats)
        self.assertEqual(len(self.messages), 2)

    def test_failed_run_after_9_pm_does_not_send_daily_report(self):
        stats = dict(completed=80, reviewed=300, source_failures=0,
                     newly_eligible=0, alerts_sent=0)
        self.execute(False, 1, now=datetime(2026, 10, 22, 21, 0, tzinfo=IST), stats=stats)
        self.assertEqual(self.messages, [])
        self.execute(True, 2, now=datetime(2026, 10, 22, 21, 15, tzinfo=IST), stats=stats)
        self.assertEqual(len(self.messages), 1)
        self.assertIn("Failed workflow runs: 1", self.messages[0])

    def test_duplicate_run_identifier_not_counted_twice(self):
        self.execute(False, 1)
        self.execute(False, 1)
        self.assertEqual(self.state["consecutive_failures"], 1)

    def test_state_json_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.json"
            write_state(path, self.state)
            self.assertEqual(load_state(path), self.state)

    def test_daily_statistics_uses_ist_day_boundaries(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "radar.sqlite3"
            db = RadarDB(path)
            db.conn.execute("INSERT INTO scan_runs (run_at,sources,failures,discovered,eligible,queued) VALUES (?,?,?,?,?,?)",
                            ("2026-10-21 18:31:00", 24, 1, 123, 2, 1))
            db.conn.execute("INSERT INTO scan_runs (run_at,sources,failures,discovered,eligible,queued) VALUES (?,?,?,?,?,?)",
                            ("2026-10-21 18:29:00", 24, 5, 200, 6, 4))
            db.conn.commit()
            db.close()
            vals = daily_statistics(path, date(2026, 10, 22))
            self.assertEqual(vals["completed"], 1)
            self.assertEqual(vals["reviewed"], 123)
            self.assertEqual(vals["source_failures"], 1)


if __name__ == "__main__":
    unittest.main()
