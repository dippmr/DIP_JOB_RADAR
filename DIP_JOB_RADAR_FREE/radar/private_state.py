"""Encrypt personal Telegram feedback/application status at rest in a PUBLIC repository."""
from __future__ import annotations

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

STATUSES = {"interested", "irrelevant", "saved", "applied", "interview", "rejected"}


class PrivateState:
    def __init__(self, path, key=None):
        self.path = Path(path)
        self.key = key or os.getenv("RADAR_STATE_KEY", "")
        self.cipher = Fernet(self.key.encode()) if self.key else None
        self.data = {"offset": 0, "feedback": {}}
        if self.path.exists():
            if not self.cipher:
                raise RuntimeError("Encrypted private state exists; RADAR_STATE_KEY is required")
            try:
                self.data = json.loads(self.cipher.decrypt(self.path.read_bytes()))
            except (InvalidToken, ValueError, json.JSONDecodeError) as error:
                raise RuntimeError("Unable to decrypt private state; check RADAR_STATE_KEY") from error

    def save(self):
        if not self.cipher:
            raise RuntimeError("Cannot persist feedback without RADAR_STATE_KEY")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        destination = self.path.with_suffix(".tmp")
        destination.write_bytes(self.cipher.encrypt(json.dumps(self.data).encode()))
        os.replace(destination, self.path)

    def set_feedback(self, fingerprint, status):
        if status not in STATUSES:
            raise ValueError("Unknown feedback status")
        self.data.setdefault("feedback", {})[fingerprint] = status
        self.save()

    def get_feedback(self, fingerprint):
        return self.data.get("feedback", {}).get(fingerprint, "")


def generate_key():
    return Fernet.generate_key().decode()
