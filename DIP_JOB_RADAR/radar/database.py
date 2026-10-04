import hashlib
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


class JobDatabase:
    def __init__(self, path: str = "data/jobs.sqlite3"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                source TEXT,
                description TEXT,
                score INTEGER,
                alerted_at TEXT,
                first_seen_at TEXT NOT NULL
            )
        """)
        self.conn.commit()

    @staticmethod
    def fingerprint(url: str, title: str = "") -> str:
        normalized = (url or "").strip().lower().rstrip("/")
        raw = normalized if normalized else (title or "").strip().lower()
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def seen(self, url: str, title: str = "") -> bool:
        fp = self.fingerprint(url, title)
        row = self.conn.execute(
            "SELECT 1 FROM jobs WHERE fingerprint = ? LIMIT 1", (fp,)
        ).fetchone()
        return row is not None

    def add(self, job, score: int, alerted: bool):
        fp = self.fingerprint(job.url, job.title)
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute("""
            INSERT OR IGNORE INTO jobs
            (fingerprint, title, url, source, description, score, alerted_at, first_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fp,
            job.title,
            job.url,
            job.source,
            job.description,
            score,
            now if alerted else None,
            now
        ))
        self.conn.commit()

    def close(self):
        self.conn.close()
