"""Publication-date checks for search results."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime


def date_status(job, now=None, max_age_days=14):
    """Return 'ok', 'missing', 'invalid', 'future' or 'old'."""
    now = now or datetime.now(UTC)

    if not job.published:
        return "missing"

    try:
        published_at = parsedate_to_datetime(job.published)

        if published_at is None:
            return "invalid"

        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)

        age = now - published_at.astimezone(UTC)

        if age < timedelta(0):
            return "future"

        if age > timedelta(days=max_age_days):
            return "old"

        return "ok"

    except (TypeError, ValueError, OverflowError):
        return "invalid"
