"""SQLite storage for jobs that were already seen or sent."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT,
    description TEXT,
    score INTEGER,
    alerted_at TEXT,
    first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP
)
"""

META_TABLE = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
)
"""

INSERT_JOB = """
INSERT OR IGNORE INTO jobs
    (fingerprint, title, url, source, description, score, alerted_at)
VALUES
    (?, ?, ?, ?, ?, ?, CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END)
"""


def normalize_url(url):
    # NOTE: do not change this or fingerprint(): every stored fingerprint
    # depends on it, and a change would make old jobs look new again.
    try:
        p = urlsplit(url)
        return urlunsplit(
            (p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", "")
        )
    except Exception:
        return url.strip()


def fingerprint(url, title):
    key = normalize_url(url) or title.strip().lower()
    return hashlib.sha256(key.encode()).hexdigest()


class JobDB:
    def __init__(self, path="data/jobs.sqlite3"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute(JOBS_TABLE)
        self.conn.execute(META_TABLE)
        self.conn.commit()

    def seen(self, fp):
        row = self.conn.execute(
            "SELECT 1 FROM jobs WHERE fingerprint = ? LIMIT 1", (fp,)
        ).fetchone()
        return row is not None

    def add(self, fp, job, score, alerted=False):
        self.conn.execute(
            INSERT_JOB,
            (
                fp,
                job.title,
                job.url,
                job.source,
                job.description,
                score,
                int(alerted),
            ),
        )
        self.conn.commit()

    def get_meta(self, key):
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def set_meta(self, key, value):
        self.conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value)
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
