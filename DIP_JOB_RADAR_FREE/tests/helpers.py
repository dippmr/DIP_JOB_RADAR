"""Small helpers shared by the tests."""

import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def real_keywords():
    return json.loads((ROOT / "config/keywords.json").read_text(encoding="utf-8"))


def make_job(
    title,
    description="",
    query="",
    published="",
    source="Example",
    url="https://example.com/job",
):
    return SimpleNamespace(
        title=title,
        description=description,
        query=query,
        published=published,
        source=source,
        url=url,
    )
