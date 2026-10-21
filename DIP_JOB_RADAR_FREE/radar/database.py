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

# V2 tables are additive; the original legacy table and fingerprints are untouched.
V2_SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
 fingerprint TEXT PRIMARY KEY,
 cluster_key TEXT NOT NULL,
 title TEXT NOT NULL,
 company TEXT NOT NULL DEFAULT '',
 location TEXT NOT NULL DEFAULT '',
 url TEXT NOT NULL,
 apply_url TEXT NOT NULL DEFAULT '',
 source TEXT NOT NULL,
 source_kind TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 published TEXT NOT NULL DEFAULT '',
 score INTEGER NOT NULL DEFAULT 0,
 verification TEXT NOT NULL DEFAULT '',
 rejection_reason TEXT NOT NULL DEFAULT '',
 reasons TEXT NOT NULL DEFAULT '[]',
 first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 last_status TEXT NOT NULL DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_opps_cluster ON opportunities(cluster_key);
CREATE INDEX IF NOT EXISTS idx_opps_seen ON opportunities(first_seen_at);
CREATE TABLE IF NOT EXISTS notification_queue (
 fingerprint TEXT PRIMARY KEY REFERENCES opportunities(fingerprint),
 state TEXT NOT NULL DEFAULT 'pending',
 attempts INTEGER NOT NULL DEFAULT 0,
 last_error TEXT NOT NULL DEFAULT '',
 sent_at TEXT,
 last_attempt_at TEXT
);
CREATE TABLE IF NOT EXISTS scan_runs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 run_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 sources INTEGER NOT NULL,
 failures INTEGER NOT NULL,
 discovered INTEGER NOT NULL,
 eligible INTEGER NOT NULL,
 queued INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS source_health (
 source TEXT PRIMARY KEY,
 success_count INTEGER NOT NULL DEFAULT 0,
 failure_count INTEGER NOT NULL DEFAULT 0,
 last_run_at TEXT,
 last_error TEXT NOT NULL DEFAULT ''
);
"""


def cluster_key(job):
    """Cross-source duplicate heuristic. Only cluster jobs with known company."""
    import re
    company = re.sub(r"[^a-z0-9]+", " ", (job.company or "").lower()).strip()
    title = re.sub(r"[^a-z0-9]+", " ", (job.title or "").lower()).strip()
    location = re.sub(r"[^a-z0-9]+", " ", (job.location or "").lower()).strip()
    if not company:
        return fingerprint(job.url, job.title)  # RSS without employer: no heuristic grouping
    return hashlib.sha256(f"{company}|{title}|{location}".encode()).hexdigest()


def job_fp(job):
    """Stable ATS IDs across application URL changes; RSS retains original legacy hash."""
    if job.source_kind == "ats" and job.external_id:
        return hashlib.sha256(job.external_id.encode()).hexdigest()
    return fingerprint(job.url, job.title)


def _v2_init(self):
    self.conn.executescript(V2_SCHEMA)
    self.conn.commit()


def _v2_record(self, job, score, verification, rejection_reason, reasons):
    import json
    fp = job_fp(job)
    ck = cluster_key(job)
    # Old `jobs` alerts are still checked by the scanner; no legacy rows are removed.
    self.conn.execute(
        """INSERT INTO opportunities
        (fingerprint, cluster_key, title, company, location, url, apply_url,
         source, source_kind, description, published, score, verification, rejection_reason, reasons)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fingerprint) DO UPDATE SET
        last_seen_at=CURRENT_TIMESTAMP, score=excluded.score,
        verification=excluded.verification, rejection_reason=excluded.rejection_reason,
        reasons=excluded.reasons, apply_url=excluded.apply_url,
        description=excluded.description, location=excluded.location,
        last_status='active'""",
        (fp, ck, job.title, job.company, job.location, job.url, job.apply_url,
         job.source, job.source_kind, job.description, job.published, score,
         verification, rejection_reason, json.dumps(reasons)),
    )
    self.conn.commit()
    return fp


def _v2_cluster_alerted(self, job):
    row = self.conn.execute(
        """SELECT 1 FROM opportunities o
        JOIN notification_queue n ON n.fingerprint=o.fingerprint
        WHERE o.cluster_key=? AND n.state IN ('pending', 'sent') LIMIT 1""",
        (cluster_key(job),),
    ).fetchone()
    return bool(row)


def _v2_queue(self, fp):
    self.conn.execute(
        "INSERT OR IGNORE INTO notification_queue(fingerprint) VALUES (?)", (fp,)
    )
    self.conn.commit()


def _v2_pending(self, limit=12):
    self.conn.row_factory = sqlite3.Row
    rows = self.conn.execute(
        """SELECT o.*, n.attempts FROM notification_queue n
        JOIN opportunities o USING (fingerprint)
        WHERE n.state = 'pending' AND n.attempts < 5
        ORDER BY o.score DESC, o.first_seen_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def _v2_sent(self, fp):
    self.conn.execute(
        "UPDATE notification_queue SET state='sent', sent_at=CURRENT_TIMESTAMP, last_error='' WHERE fingerprint=?",
        (fp,),
    )
    self.conn.commit()


def _v2_failed(self, fp, error):
    # Never store HTTP error URLs: bot credentials are in those URLs.
    self.conn.execute(
        """UPDATE notification_queue SET attempts=attempts+1,
           last_attempt_at=CURRENT_TIMESTAMP, last_error=? WHERE fingerprint=?""",
        (str(type(error).__name__)[:60], fp),
    )
    self.conn.commit()


def _v2_source(self, name, success, error=""):
    self.conn.execute(
        """INSERT INTO source_health(source,success_count,failure_count,last_run_at,last_error)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
        ON CONFLICT(source) DO UPDATE SET
        success_count=source_health.success_count + excluded.success_count,
        failure_count=source_health.failure_count + excluded.failure_count,
        last_run_at=CURRENT_TIMESTAMP, last_error=excluded.last_error""",
        (name, int(success), int(not success), str(error)[:150] if error else ""),
    )
    self.conn.commit()


def _v2_run(self, sources, failures, discovered, eligible, queued):
    self.conn.execute(
        "INSERT INTO scan_runs(sources,failures,discovered,eligible,queued) VALUES (?,?,?,?,?)",
        (sources, failures, discovered, eligible, queued),
    )
    self.conn.commit()


def _v2_jobs(self, limit=500, include_rejected=True):
    self.conn.row_factory = sqlite3.Row
    query = "SELECT * FROM opportunities"
    if not include_rejected:
        query += " WHERE rejection_reason=''"
    return [dict(row) for row in self.conn.execute(query + " ORDER BY first_seen_at DESC LIMIT ?", (limit,))]


def _v2_stats(self, days=7):
    since = f"-{int(days)} days"
    out = {}
    for name, sql in (
        ("discovered", "SELECT COUNT(*) FROM opportunities WHERE first_seen_at >= datetime('now', ?)"),
        ("qualified", "SELECT COUNT(*) FROM opportunities WHERE first_seen_at >= datetime('now', ?) AND rejection_reason=''"),
        ("alerts_sent", "SELECT COUNT(*) FROM notification_queue WHERE sent_at >= datetime('now', ?)"),
    ):
        out[name] = self.conn.execute(sql, (since,)).fetchone()[0]
    out["sources"] = [dict(zip(("source", "ok", "fail"), row)) for row in self.conn.execute(
        "SELECT source, success_count, failure_count FROM source_health ORDER BY success_count DESC"
    )]
    out["runs"] = self.conn.execute("SELECT COUNT(*) FROM scan_runs WHERE run_at >= datetime('now', ?)", (since,)).fetchone()[0]
    return out


class RadarDB(JobDB):
    """Add V2 tables/methods without changing the legacy JobDB API."""

    def __init__(self, path="data/jobs.sqlite3"):
        super().__init__(path)
        _v2_init(self)

    record_opportunity = _v2_record
    cluster_alerted = _v2_cluster_alerted
    queue_alert = _v2_queue
    pending_alerts = _v2_pending
    mark_alert_sent = _v2_sent
    mark_alert_failed = _v2_failed
    record_source = _v2_source
    record_run = _v2_run
    list_opportunities = _v2_jobs
    stats = _v2_stats

    def mark_closed_board_jobs(self, board_source, fresh_fingerprints):
        """Mark jobs missing from a SUCCESSFULLY fetched public board as closed/unlisted.

        A failed request must never cause jobs to be marked inactive.
        """
        fresh = set(fresh_fingerprints)
        known = self.conn.execute(
            "SELECT fingerprint FROM opportunities WHERE source=? AND source_kind='ats' AND last_status='active'",
            (board_source,),
        ).fetchall()
        for (fp,) in known:
            if fp not in fresh:
                self.conn.execute(
                    "UPDATE opportunities SET last_status='not_seen_on_board' WHERE fingerprint=?",
                    (fp,),
                )
        self.conn.commit()
