from datetime import datetime

import pytest

from radar import notify
from radar.database import JobDB
from radar.notify import IST, maybe_send_feed_alert, maybe_send_heartbeat


@pytest.fixture
def sent(monkeypatch):
    messages = []
    monkeypatch.setattr(
        notify, "send_message", lambda token, chat, text: messages.append(text)
    )
    return messages


@pytest.fixture
def db(tmp_path):
    database = JobDB(tmp_path / "jobs.sqlite3")
    yield database
    database.close()


def at(day, hour):
    return datetime(2026, 10, day, hour, 0, tzinfo=IST)


def test_heartbeat_waits_until_9am_ist(db, sent):
    assert maybe_send_heartbeat(db, "t", "c", "s", now=at(21, 8)) is False
    assert sent == []


def test_heartbeat_sends_once_per_day(db, sent):
    assert maybe_send_heartbeat(db, "t", "c", "summary", now=at(21, 9)) is True
    assert maybe_send_heartbeat(db, "t", "c", "summary", now=at(21, 15)) is False
    assert maybe_send_heartbeat(db, "t", "c", "summary", now=at(22, 9)) is True
    assert len(sent) == 2
    assert "alive" in sent[0]


def test_feed_alert_is_limited_to_once_per_day(db, sent):
    assert maybe_send_feed_alert(db, "t", "c", 40, 46, now=at(21, 3)) is True
    assert maybe_send_feed_alert(db, "t", "c", 40, 46, now=at(21, 4)) is False
    assert maybe_send_feed_alert(db, "t", "c", 40, 46, now=at(22, 3)) is True
    assert "40 of 46" in sent[0]


def test_failed_send_does_not_crash_and_is_retried(db, monkeypatch):
    def boom(token, chat, text):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(notify, "send_message", boom)
    assert maybe_send_heartbeat(db, "t", "c", "s", now=at(21, 10)) is False
    assert db.get_meta("last_heartbeat") is None  # so the next run tries again
