from datetime import UTC, datetime

from radar.dates import date_status
from tests.helpers import make_job

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def status(published, **kwargs):
    return date_status(make_job("x", published=published), now=NOW, **kwargs)


def test_recent_is_ok():
    assert status("Mon, 19 Oct 2026 10:00:00 GMT") == "ok"


def test_old():
    assert status("Mon, 01 Jun 2020 10:00:00 GMT") == "old"


def test_future():
    assert status("Sat, 31 Oct 2026 10:00:00 GMT") == "future"


def test_missing():
    assert status("") == "missing"


def test_invalid():
    assert status("not a date") == "invalid"


def test_age_limit_is_configurable():
    published = "Mon, 12 Oct 2026 10:00:00 GMT"  # 9 days old
    assert status(published, max_age_days=14) == "ok"
    assert status(published, max_age_days=7) == "old"
