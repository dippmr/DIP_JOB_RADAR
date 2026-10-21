import sqlite3

import pytest

from radar.database import JobDB, fingerprint
from tests.helpers import make_job

# Hashes produced by the ORIGINAL code. If these change, every job already in
# data/jobs.sqlite3 would look new again and be re-sent to Telegram.
KNOWN_FINGERPRINTS = [
    (
        "https://news.google.com/rss/articles/CBMiABC?oc=5",
        "T1",
        "bf21700a949d908d23a8e423cde11c95f0073e5c81945e34d8da8b5d04d0eed3",
    ),
    (
        "https://example.com/Job/",
        "T2",
        "fe3c638f32532d05955b8efa9f1f6aa18369515466f164e32e7b7156bc8a6e54",
    ),
    (
        "",
        "Only Title  ",
        "4b504a007193e1b48b96cce62f23a53e06ccbc680373081a2a111a00793800da",
    ),
    (
        "HTTP://Example.COM/a/b/?x=1#f",
        "T3",
        "649028aa54628de9cc4089da00b02c834875c6e987349bb5c20c6803d5fa2e05",
    ),
]


@pytest.mark.parametrize("url,title,expected", KNOWN_FINGERPRINTS)
def test_fingerprint_is_stable(url, title, expected):
    assert fingerprint(url, title) == expected


def test_add_and_seen(tmp_path):
    db = JobDB(tmp_path / "jobs.sqlite3")
    job = make_job("UI Designer")
    fp = fingerprint(job.url, job.title)
    assert not db.seen(fp)
    db.add(fp, job, 80, alerted=True)
    assert db.seen(fp)
    db.close()


def test_meta_roundtrip(tmp_path):
    db = JobDB(tmp_path / "jobs.sqlite3")
    assert db.get_meta("k") is None
    db.set_meta("k", "v1")
    db.set_meta("k", "v2")
    assert db.get_meta("k") == "v2"
    db.close()


def test_existing_database_keeps_its_rows(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "fingerprint TEXT UNIQUE NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL, "
        "source TEXT, description TEXT, score INTEGER, alerted_at TEXT, "
        "first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    con.execute(
        "INSERT INTO jobs (fingerprint, title, url) VALUES ('abc', 't', 'https://x')"
    )
    con.commit()
    con.close()

    db = JobDB(path)
    assert db.seen("abc")
    db.close()
