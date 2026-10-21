"""Consistent SQLite snapshot for GitHub Actions backup artifact (not committed)."""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def backup(output_folder=None):
    output = Path(output_folder or ROOT / "tmp" / "backup")
    output.mkdir(parents=True, exist_ok=True)
    source = ROOT / "data" / "jobs.sqlite3"
    if not source.exists():
        raise FileNotFoundError("No job database; run a scan first")
    source_db = sqlite3.connect(source)
    target_db = sqlite3.connect(output / "jobs.sqlite3")
    try:
        source_db.backup(target_db)
    finally:
        target_db.close()
        source_db.close()
    encrypted = ROOT / "data" / "private_state.enc"
    if encrypted.exists():
        shutil.copy2(encrypted, output / "private_state.enc")
    return output


if __name__ == "__main__":
    print("Created backup at:", backup())
