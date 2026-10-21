from datetime import UTC, datetime

import pytest

from radar.__main__ import classify, collect_jobs
from radar.database import JobDB, fingerprint
from search.rss_search import SearchResult
from tests.helpers import real_keywords

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
FRESH = "Mon, 19 Oct 2026 10:00:00 GMT"
OLD = "Mon, 01 Jun 2020 10:00:00 GMT"


def result(title, published=FRESH, query='"Ahmedabad" hiring', description=""):
    url = "https://example.com/" + title.replace(" ", "-")
    return SearchResult(title, url, description, published, "Example", query)


class FakeSearcher:
    def __init__(self, failing=()):
        self.failing = set(failing)

    def search(self, query, limit):
        if query in self.failing:
            raise RuntimeError("blocked")
        return [result(f"Designer for {query}")]


@pytest.fixture
def db(tmp_path):
    database = JobDB(tmp_path / "jobs.sqlite3")
    yield database
    database.close()


def run(jobs, db, dry=False, threshold=60):
    all_jobs = {fingerprint(j.url, j.title): j for j in jobs}
    return classify(all_jobs, db, real_keywords(), threshold, dry, now=NOW)


def test_collect_counts_failed_feeds():
    jobs, failures = collect_jobs(FakeSearcher(failing={"b"}), ["a", "b", "c"], 15)
    assert failures == 1
    assert len(jobs) == 2


def test_collect_reports_total_failure():
    _, failures = collect_jobs(FakeSearcher(failing={"a", "b"}), ["a", "b"], 15)
    assert failures == 2


def test_good_job_matches_and_old_job_is_skipped(db):
    good = result(
        "Junior UI/UX Designer - Ahmedabad",
        description="We are hiring. Figma, wireframes, prototype.",
    )
    old = result("Junior UI/UX Designer - Ahmedabad (old)", published=OLD)
    out = run([good, old], db)
    assert [m[1].title for m in out.matches] == [good.title]
    assert out.date_counts["old"] == 1


def test_job_without_city_anywhere_is_skipped(db):
    job = result("UI/UX Designer hiring in Mumbai", query="designer hiring")
    out = run([job], db)
    assert out.skipped_location == 1
    assert out.matches == []


def test_city_only_in_query_is_kept_as_weak(db):
    job = result(
        "UI/UX Designer - we are hiring",
        description="Figma, wireframes, prototype.",
        query='"Ahmedabad" "UI/UX Designer" hiring',
    )
    out = run([job], db)
    assert out.weak_location == 1
    assert len(out.matches) == 1
    assert out.matches[0][2].location == "weak"


def test_already_sent_jobs_are_skipped_but_not_in_dry_run(db):
    job = result(
        "Junior UI/UX Designer - Ahmedabad",
        description="We are hiring. Figma, wireframes, prototype.",
    )
    first = run([job], db)
    fp, _, scored = first.matches[0]
    db.add(fp, job, scored.score, True)

    assert run([job], db).skipped_seen == 1
    assert len(run([job], db, dry=True).matches) == 1
