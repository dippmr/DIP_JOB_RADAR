"""V2 matching regression tests: offline, no real network or Telegram sends."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from radar.matching import evaluate
from radar.verification import evaluate_location, required_years, role_groups, verify_job
from search.ats import parse_ashby, parse_lever
from search.rss_search import SearchResult

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / 'config/profile.json').read_text())
KEYWORDS = json.loads((ROOT / 'config/keywords.json').read_text())


def job(title='Graphic Designer', location='Ahmedabad', description='Figma and prototyping',
        work_mode='', source_kind='ats', apply_url='https://example.com/apply', company='Test'):
    return SearchResult(title, 'https://example.com/jobs/role-123', description,
                        company=company, location=location, work_mode=work_mode,
                        source_kind=source_kind, apply_url=apply_url)


class RoleMatchingTests(unittest.TestCase):
    def test_role_title_aliases(self):
        for title in (
            'UI/UX Designer', 'UX/UI Designer', 'UI UX Designer', 'UX-UI Designer',
            'User Experience Designer', 'User Interface Designer',
            'Associate Product Designer', 'Junior Graphic Designer',
            'Graphics Designer', 'Visual Designer (Contractor)',
            'Interaction Designer', 'Digital Product Designer',
        ):
            with self.subTest(title=title):
                result = evaluate(job(title=title), PROFILE, KEYWORDS)
                self.assertTrue(result.accepted, result.rejection)
                self.assertGreaterEqual(result.score, 65)

    def test_disallow_non_designer_titles(self):
        for title in ('IT Manager', 'Design Engineer', 'UX Researcher', 'Content Writer',
                      'Sales Executive', 'Video Editor', 'Product Manager'):
            with self.subTest(title=title):
                self.assertFalse(evaluate(job(title=title), PROFILE, KEYWORDS).accepted)

    def test_senior_intern_courses_excluded(self):
        for title in ('Senior Graphic Designer', 'Lead Visual Designer',
                      'Principal UI Designer', 'Graphic Designer Internship',
                      'UI/UX Designer Training Course', 'Design Manager'):
            with self.subTest(title=title):
                self.assertFalse(evaluate(job(title=title), PROFILE, KEYWORDS).accepted)

    def test_explicit_preferences_not_bypassed_by_keyword_list(self):
        restricted = {**PROFILE, 'preferred_roles': ['ui/ux designer']}
        self.assertFalse(evaluate(job('Graphic Designer'), restricted, KEYWORDS).accepted)
        self.assertTrue(evaluate(job('UX Designer'), restricted, KEYWORDS).accepted)
        self.assertFalse(evaluate(job('UI Designer'), {**PROFILE, 'preferred_roles': []}, KEYWORDS).accepted)

    def test_only_user_preferred_skills_count(self):
        restricted = {**PROFILE, 'skills': ['photoshop']}
        result = evaluate(job(description='Figma and prototyping'), restricted, KEYWORDS)
        self.assertTrue(result.accepted)
        self.assertFalse(any(reason.startswith('Skills:') for reason in result.reasons))


class LocationMatchingTests(unittest.TestCase):
    def test_preferred_cities_work(self):
        for location in ('Ahmedabad, Gujarat', 'Gandhinagar, Gujarat', 'Ahmedabad (Hybrid)'):
            with self.subTest(location=location):
                self.assertTrue(evaluate(job(location=location), PROFILE, KEYWORDS).accepted)

    def test_remote_india_evidence(self):
        scenarios = (
            ('Remote - India', '', ''),
            ('India', 'Fully remote position', ''),
            ('India', '', 'remote'),
            ('Remote', 'Work remotely from anywhere in India.', ''),
            ('Remote', 'Candidates must be located in India.', ''),
            ('', 'This is a remote position based in India.', ''),
            ('Worldwide', 'Remote in India; must be based in India.', ''),
        )
        for loc, desc, mode in scenarios:
            with self.subTest(location=loc, description=desc):
                outcome = evaluate(job(location=loc, description=desc, work_mode=mode), PROFILE, KEYWORDS)
                self.assertTrue(outcome.accepted, outcome.rejection)

    def test_conservative_location_exclusions(self):
        scenarios = (
            ('India', 'Figma design tools', ''),
            ('United States', 'Remote - USA / working with India team', ''),
            ('Remote - US', 'Working with teammates in India', ''),
            ('Remote', 'All applicants welcome; remote team worldwide', ''),
            ('Bangalore', 'Collaborate with remote staff in India', ''),
            ('Mumbai (Onsite)', 'Remote collaboration tools in India', ''),
            ('India', 'Remote work is not available', ''),
        )
        for loc, desc, mode in scenarios:
            with self.subTest(location=loc, description=desc):
                self.assertFalse(evaluate(job(location=loc, description=desc, work_mode=mode), PROFILE, KEYWORDS).accepted)

    def test_hybrid_can_be_disabled(self):
        restricted = {**PROFILE, 'allow_hybrid': False}
        self.assertFalse(evaluate(job(location='Gandhinagar (Hybrid)'), restricted, KEYWORDS).accepted)

    def test_remote_can_be_disabled(self):
        restricted = {**PROFILE, 'allow_remote_india': False}
        self.assertFalse(evaluate(job(location='Remote - India'), restricted, KEYWORDS).accepted)

    def test_rss_query_city_not_evidence(self):
        lead = job(location='', source_kind='rss', apply_url='', description='We are hiring')
        lead.query = 'Ahmedabad Graphic Designer hiring'
        self.assertFalse(evaluate_location(lead, PROFILE)[0])

    def test_remote_generic_requires_india(self):
        self.assertFalse(evaluate_location(job(location='Remote', work_mode='remote'), PROFILE)[0])


class VerificationTests(unittest.TestCase):
    def test_minimum_experience_not_range_maximum(self):
        self.assertEqual(required_years('Requires 2–5 years of experience'), 2)
        self.assertEqual(required_years('Experience: 4+ years'), 4)
        self.assertEqual(required_years('We need 5-7 years'), 5)
        self.assertIsNone(required_years('Our company has 22 years in India'))

    def test_required_seniority_rejected(self):
        self.assertFalse(evaluate(job(description='Experience: 5+ years'), PROFILE, KEYWORDS).accepted)

    def test_individual_ats_and_safe_links_required(self):
        self.assertFalse(verify_job(job(apply_url=''), PROFILE).accepted)
        self.assertFalse(verify_job(job(), {**PROFILE, 'excluded_companies': ['Test']}).accepted)
        lead = job(source_kind='rss', apply_url='', description='Hiring graphic designer')
        self.assertFalse(verify_job(lead, PROFILE).accepted)
        self.assertTrue(verify_job(lead, {**PROFILE, 'allow_unverified_rss': True}).accepted)

    def test_legacy_scoring_does_not_affect_remote_ats(self):
        result = evaluate(job(title='Graphic Designer', location='Remote - India', description=''), PROFILE, KEYWORDS)
        self.assertTrue(result.accepted)
        self.assertGreaterEqual(result.score, 65)


class ATSWorkModeTests(unittest.TestCase):
    def test_ashby_is_remote_field_extracted(self):
        data = {'jobs': [{'id': '1', 'title': 'Visual Designer',
                         'jobUrl': 'https://jobs.ashbyhq.com/demo/1',
                         'location': 'India', 'isRemote': True}]}
        parsed = list(parse_ashby(data, 'Demo', 'demo'))[0]
        self.assertEqual(parsed.work_mode, 'remote')
        self.assertTrue(evaluate(parsed, PROFILE, KEYWORDS).accepted)

    def test_lever_workplace_type_extracted(self):
        data = [{'id': '1', 'text': 'Graphic Designer',
                 'hostedUrl': 'https://jobs.lever.co/demo/1',
                 'applyUrl': 'https://jobs.lever.co/demo/1/apply',
                 'categories': {'location': 'India'}, 'workplaceType': 'remote'}]
        parsed = list(parse_lever(data, 'Demo', 'demo'))[0]
        self.assertEqual(parsed.work_mode, 'remote')
        self.assertTrue(evaluate(parsed, PROFILE, KEYWORDS).accepted)


class ScannerIntegrationTests(unittest.TestCase):
    def test_full_scanner_with_synthetic_ats_jobs(self):
        # Full V2 scan pipeline, using synthetic vacancies, no network or Telegram.
        from radar.database import RadarDB
        from radar.v2 import scan
        from unittest.mock import patch

        candidates = [
            job(title='Graphic Designer', location='Gandhinagar', description='Figma'),
            job(title='Visual Designer', location='India', description='Fully remote role'),
            job(title='Senior Product Designer', location='Ahmedabad'),
        ]
        for idx, candidate in enumerate(candidates):
            candidate.url = f'https://example.com/jobs/{idx}'
            candidate.apply_url = f'https://example.com/jobs/{idx}/apply'
            candidate.external_id = f'test:{idx}'
        db = RadarDB(':memory:')
        try:
            with patch.dict('os.environ', {'MIN_SCORE': '65'}):
                total, eligible, queued, rejected = scan(db, PROFILE, KEYWORDS, candidates, dry=False)
            self.assertEqual(total, 3)
            self.assertEqual(eligible, 2)
            self.assertEqual(queued, 2)
            self.assertEqual(sum(rejected.values()), 1)
        finally:
            db.close()


if __name__ == '__main__':
    unittest.main()
